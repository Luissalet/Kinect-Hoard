#include <libfreenect.h>
#include <libfreenect_registration.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#ifdef _WIN32
#include <windows.h>
#endif

#ifdef _WIN32
#define KH_API __declspec(dllexport)
#else
#define KH_API
#endif

typedef struct {
    freenect_context *context;
    freenect_device *device;
    uint8_t *latest;
    uint8_t *latest_rgb;
    uint8_t *snapshot_depth;
    uint8_t *snapshot_rgb;
    int capacity;
    int depth_bytes;
    int rgb_bytes;
    int width;
    int height;
    int frame_bytes;
    int kind;
    uint32_t timestamp;
    uint64_t sequence;
    uint64_t delivered;
    uint64_t video_sequence;
    uint64_t video_delivered;
    int depth_started;
    int video_started;
#ifdef _WIN32
    HANDLE worker;
    CRITICAL_SECTION frame_lock;
    int lock_initialized;
    volatile LONG running;
    int event_error;
#endif
} kh360_session;

static FILE *diagnostic_log;

static void on_log(freenect_context *context, freenect_loglevel level, const char *message) {
    (void)context;
    if (!diagnostic_log) return;
    fprintf(diagnostic_log, "libfreenect[%d] %s", (int)level, message);
    fflush(diagnostic_log);
}

static void set_error(char *target, int capacity, const char *message, int code) {
    if (target && capacity > 0) {
        snprintf(target, (size_t)capacity, "%s (%d)", message, code);
        target[capacity - 1] = 0;
    }
}

static void on_depth(freenect_device *device, void *data, uint32_t timestamp) {
    kh360_session *session = (kh360_session *)freenect_get_user(device);
    if (!session || (session->kind != 1 && session->kind != 3)) return;
#ifdef _WIN32
    EnterCriticalSection(&session->frame_lock);
#endif
    memcpy(session->latest, data, (size_t)(session->kind == 3 ? session->depth_bytes : session->frame_bytes));
    session->timestamp = timestamp;
    session->sequence++;
#ifdef _WIN32
    LeaveCriticalSection(&session->frame_lock);
#endif
}

static void on_video(freenect_device *device, void *data, uint32_t timestamp) {
    kh360_session *session = (kh360_session *)freenect_get_user(device);
    if (!session || session->kind == 1) return;
#ifdef _WIN32
    EnterCriticalSection(&session->frame_lock);
#endif
    if (session->kind == 3) {
        memcpy(session->latest_rgb, data, (size_t)session->rgb_bytes);
        session->video_sequence++;
    } else {
        memcpy(session->latest, data, (size_t)session->frame_bytes);
        session->sequence++;
    }
    session->timestamp = timestamp;
#ifdef _WIN32
    LeaveCriticalSection(&session->frame_lock);
#endif
}

#ifdef _WIN32
static DWORD WINAPI pump_events(LPVOID parameter) {
    kh360_session *session = (kh360_session *)parameter;
    while (InterlockedCompareExchange(&session->running, 0, 0)) {
        struct timeval wait_time = { 0, 20000 };
        int rc = freenect_process_events_timeout(session->context, &wait_time);
        if (rc < 0) {
            EnterCriticalSection(&session->frame_lock);
            session->event_error = rc;
            LeaveCriticalSection(&session->frame_lock);
            break;
        }
    }
    return 0;
}
#endif

KH_API void kh360_close(kh360_session *session) {
    if (!session) return;
#ifdef _WIN32
    if (session->worker) {
        InterlockedExchange(&session->running, 0);
        WaitForSingleObject(session->worker, INFINITE);
        CloseHandle(session->worker);
    }
#endif
    if (session->device) {
        if (session->depth_started) freenect_stop_depth(session->device);
        if (session->video_started) freenect_stop_video(session->device);
        freenect_close_device(session->device);
    }
    if (session->context) freenect_shutdown(session->context);
    if (diagnostic_log) { fclose(diagnostic_log); diagnostic_log = NULL; }
#ifdef _WIN32
    if (session->lock_initialized) DeleteCriticalSection(&session->frame_lock);
#endif
    free(session->latest);
    free(session->latest_rgb);
    free(session->snapshot_depth);
    free(session->snapshot_rgb);
    free(session);
}

// kind: 0 RGB, 1 depth in millimetres, 2 eight-bit infrared, 3 registered RGB + depth.
KH_API kh360_session *kh360_open(int kind, int index, char *error, int error_capacity) {
    kh360_session *session;
    freenect_frame_mode mode;
    int rc;
    if (kind < 0 || kind > 3) {
        set_error(error, error_capacity, "Unsupported stream", kind);
        return NULL;
    }
    session = (kh360_session *)calloc(1, sizeof(*session));
    if (!session) {
        set_error(error, error_capacity, "Out of memory", -1);
        return NULL;
    }
    session->kind = kind;
#ifdef _WIN32
    InitializeCriticalSection(&session->frame_lock);
    session->lock_initialized = 1;
#endif
    rc = freenect_init(&session->context, NULL);
    if (rc < 0) {
        set_error(error, error_capacity, "freenect_init", rc);
        kh360_close(session);
        return NULL;
    }
    {
        const char *log_path = getenv("KH360_LOG");
        if (log_path && *log_path) {
            diagnostic_log = fopen(log_path, "a");
            if (diagnostic_log) {
                freenect_set_log_callback(session->context, on_log);
                freenect_set_log_level(session->context, FREENECT_LOG_DEBUG);
            }
        }
    }
    freenect_select_subdevices(session->context, FREENECT_DEVICE_CAMERA);
    rc = freenect_open_device(session->context, &session->device, index);
    if (rc < 0) {
        set_error(error, error_capacity, "freenect_open_device; check libusbK on USB 045E:02AE", rc);
        kh360_close(session);
        return NULL;
    }
    freenect_set_user(session->device, session);
    if (kind == 1 || kind == 3) {
        mode = freenect_find_depth_mode(FREENECT_RESOLUTION_MEDIUM, FREENECT_DEPTH_MM);
        rc = mode.is_valid ? freenect_set_depth_mode(session->device, mode) : -1;
        freenect_set_depth_callback(session->device, on_depth);
        if (kind == 3 && rc >= 0) {
            freenect_frame_mode rgb_mode = freenect_find_video_mode(FREENECT_RESOLUTION_MEDIUM, FREENECT_VIDEO_RGB);
            rc = rgb_mode.is_valid ? freenect_set_video_mode(session->device, rgb_mode) : -1;
            freenect_set_video_callback(session->device, on_video);
            if (rc >= 0) session->rgb_bytes = rgb_mode.bytes;
        }
    } else {
        mode = freenect_find_video_mode(FREENECT_RESOLUTION_MEDIUM,
            kind == 0 ? FREENECT_VIDEO_RGB : FREENECT_VIDEO_IR_8BIT);
        rc = mode.is_valid ? freenect_set_video_mode(session->device, mode) : -1;
        freenect_set_video_callback(session->device, on_video);
    }
    if (rc < 0) {
        set_error(error, error_capacity, "freenect_set_mode", rc);
        kh360_close(session);
        return NULL;
    }
    session->width = mode.width;
    session->height = mode.height;
    session->depth_bytes = (kind == 1 || kind == 3) ? mode.bytes : 0;
    session->frame_bytes = kind == 3 ? mode.bytes + session->rgb_bytes : mode.bytes;
    session->capacity = session->frame_bytes;
    session->latest = (uint8_t *)malloc((size_t)mode.bytes);
    if (kind == 3) {
        session->latest_rgb = (uint8_t *)malloc((size_t)session->rgb_bytes);
        session->snapshot_depth = (uint8_t *)malloc((size_t)session->depth_bytes);
        session->snapshot_rgb = (uint8_t *)malloc((size_t)session->rgb_bytes);
    }
    if (!session->latest || (kind == 3 && (!session->latest_rgb || !session->snapshot_depth || !session->snapshot_rgb))) {
        set_error(error, error_capacity, "Out of memory", -1);
        kh360_close(session);
        return NULL;
    }
    rc = (kind == 1 || kind == 3) ? freenect_start_depth(session->device) : freenect_start_video(session->device);
    if (rc < 0) {
        set_error(error, error_capacity, "freenect_start_stream", rc);
        kh360_close(session);
        return NULL;
    }
    if (kind == 1 || kind == 3) session->depth_started = 1;
    else session->video_started = 1;
    if (kind == 3) {
        rc = freenect_start_video(session->device);
        if (rc < 0) {
            set_error(error, error_capacity, "freenect_start_video", rc);
            kh360_close(session);
            return NULL;
        }
        session->video_started = 1;
    }
#ifdef _WIN32
    InterlockedExchange(&session->running, 1);
    session->worker = CreateThread(NULL, 0, pump_events, session, 0, NULL);
    if (!session->worker) {
        InterlockedExchange(&session->running, 0);
        set_error(error, error_capacity, "Cannot start USB event thread", (int)GetLastError());
        kh360_close(session);
        return NULL;
    }
#endif
    return session;
}

KH_API int kh360_width(const kh360_session *session) { return session ? session->width : 0; }
KH_API int kh360_height(const kh360_session *session) { return session ? session->height : 0; }
KH_API int kh360_frame_bytes(const kh360_session *session) { return session ? session->frame_bytes : 0; }

KH_API int kh360_depth_intrinsics(kh360_session *session, float *fx, float *fy) {
    double x, y;
    if (!session || !session->device || !fx || !fy || (session->kind != 1 && session->kind != 3)) return 0;
    freenect_camera_to_world(session->device, 321, 241, 1000, &x, &y);
    if (x <= 0 || y <= 0) return 0;
    *fx = (float)(1000.0 / x);
    *fy = (float)(1000.0 / y);
    return 1;
}

KH_API int kh360_project_depth(kh360_session *session, const uint16_t *depth_mm,
    int count, float *xyz, int xyz_capacity) {
    int i;
    if (!session || !session->device || (session->kind != 1 && session->kind != 3) || !depth_mm || !xyz ||
        count != session->width * session->height || xyz_capacity < count * 3) return 0;
    for (i = 0; i < count; i++) {
        uint16_t z = depth_mm[i];
        int j = i * 3;
        if (z == 0 || z > 10000) {
            xyz[j] = xyz[j + 1] = xyz[j + 2] = NAN;
        } else {
            double x, y;
            freenect_camera_to_world(session->device, i % session->width,
                i / session->width, z, &x, &y);
            xyz[j] = (float)(x / 1000.0);
            xyz[j + 1] = (float)(-y / 1000.0);
            xyz[j + 2] = z / 1000.0f;
        }
    }
    return 1;
}

// Returns 1 for a fresh frame, 0 while waiting, or a negative libusb error.
KH_API int kh360_read(kh360_session *session, uint8_t *target, int capacity, uint32_t *timestamp) {
#ifndef _WIN32
    struct timeval wait_time;
    int rc;
#endif
    if (!session || !target || capacity < session->frame_bytes) return -100;
#ifdef _WIN32
    EnterCriticalSection(&session->frame_lock);
    if (session->event_error < 0) {
        int error = session->event_error;
        LeaveCriticalSection(&session->frame_lock);
        return error;
    }
    if (session->sequence == session->delivered ||
        (session->kind == 3 && session->video_sequence == session->video_delivered)) {
        LeaveCriticalSection(&session->frame_lock);
        return 0;
    }
#else
    wait_time.tv_sec = 0;
    wait_time.tv_usec = 20000;
    rc = freenect_process_events_timeout(session->context, &wait_time);
    if (rc < 0) return rc;
    if (session->sequence == session->delivered ||
        (session->kind == 3 && session->video_sequence == session->video_delivered)) return 0;
#endif
    if (session->kind == 3) {
        memcpy(session->snapshot_depth, session->latest, (size_t)session->depth_bytes);
        memcpy(session->snapshot_rgb, session->latest_rgb, (size_t)session->rgb_bytes);
    } else {
        memcpy(target, session->latest, (size_t)session->frame_bytes);
    }
    if (timestamp) *timestamp = session->timestamp;
    session->delivered = session->sequence;
    if (session->kind == 3) session->video_delivered = session->video_sequence;
#ifdef _WIN32
    LeaveCriticalSection(&session->frame_lock);
#endif
    if (session->kind == 3) {
        memcpy(target, session->snapshot_depth, (size_t)session->depth_bytes);
        freenect_map_rgb_to_depth(session->device, (uint16_t *)session->snapshot_depth,
            session->snapshot_rgb, target + session->depth_bytes);
    }
    return 1;
}
