Frontend Modularization

Create base.html for the main chassis and navigation.

Move all style tags to static/css/style.css.

Move all script tags to static/js/joystick.js.

Build one master button component that accepts color and label variables.

Backend and Configuration

Create config.json in the root directory.

Store absolute file paths, IP addresses, and joystick tuning parameters here.

Strip app.py down to only handle URL routing.

Move OS execution logic into a new system_commands.py file.

Critical Security and Stability Issues

Standardize file names to lowercase with underscores.

Add error catching to JavaScript fetch requests to handle dropped packets.

Add local authentication. Currently, anyone on the Wi-Fi can shut down the machine.

Replace the .vbs startup hack with a proper background Windows Service.