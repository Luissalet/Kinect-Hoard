% Kinect Hoard HTTP bridge for MATLAB. Start the Hoard server with Color.
% KinectHoard.App.exe --webserver 8765 Color 0
% Press Ctrl+C in MATLAB to stop. Requires Image Processing Toolbox for imshow.
base = 'http://127.0.0.1:8765';
destination = [tempname, '.png'];
cleanup = onCleanup(@() delete(destination));
window = figure('Name', 'Kinect Hoard / MATLAB');
while ishandle(window)
    try
        frame = webread([base, '/api/frame']);
        websave(destination, [base, '/frame.png']);
        image = imread(destination);
        imshow(image);
        title(sprintf('%s %d x %d', frame.stream, size(image, 2), size(image, 1)));
        drawnow;
    catch exception
        fprintf('Esperando el servidor: %s\n', exception.message);
        pause(0.5);
    end
end
