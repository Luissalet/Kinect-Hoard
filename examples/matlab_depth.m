% Kinect Hoard raw uint16 bridge for MATLAB.
% Start: KinectHoard.App.exe --webserver 8765 Depth 0
% Supports Depth, Infrared, LongExposureInfrared, BodyIndex and ColorDepth.
base = 'http://127.0.0.1:8765';
destination = [tempname, '.raw'];
cleanup = onCleanup(@() delete(destination));
window = figure('Name', 'Kinect Hoard / MATLAB raw depth');
while ishandle(window)
    try
        frame = webread([base, '/api/frame']);
        if ~strcmp(frame.raw_format, 'uint16_le')
            error('El flujo actual no entrega uint16. Selecciona profundidad, IR o BodyIndex.');
        end
        websave(destination, [base, '/frame.raw']);
        file = fopen(destination, 'r', 'ieee-le');
        if file < 0
            error('No se pudo abrir el fotograma binario.');
        end
        data = fread(file, double(frame.width) * double(frame.height), 'uint16=>uint16');
        fclose(file);
        if numel(data) ~= double(frame.width) * double(frame.height)
            error('Fotograma incompleto: %d muestras.', numel(data));
        end
        image = reshape(data, [double(frame.width), double(frame.height)])';
        imagesc(image);
        axis image off;
        colormap(gray);
        colorbar;
        title(sprintf('%s %d x %d (%s)', frame.stream, frame.width, frame.height, frame.raw_unit));
        drawnow;
    catch exception
        fprintf('Esperando el servidor: %s\n', exception.message);
        pause(0.5);
    end
end
