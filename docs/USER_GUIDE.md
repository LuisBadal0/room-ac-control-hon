# Using Room AC Control

Launch with **Start Room AC Control.cmd** or the local app-icon shortcut. Sign in using the cloud account email/password account that already controls the AC on your phone. **Remember me on this computer** enables encrypted automatic sign-in after the first successful login.

Remember me is off by default. Enabling it saves your actual email and password using Windows encryption; other programs running as your Windows user can decrypt them. Existing remembered accounts retain their previous choice. Your password is passed to pyhOn for authentication.

During manual or automatic sign-in, a rotating loading ring appears while your account connects and AC settings load. The form returns if sign-in fails, so you can retry. Closing the application stops the animation.

## Select an AC

The room card shows the active AC's name and model. Accounts with several units have a **Switch** button: choose a room tile to load its status. A single unit displays its connection status directly. Room names come from your cloud account.

## Set comfort controls

Move the temperature slider, use plus/minus, or select Mode, Fan speed, Sleep and Airflow. Changes are staged until you click **Apply changes**. Applying changes preserves the AC's power state.

Airflow position icons show the louver opening progressively: Position 1 is the most closed and Position 5 is the most open. Swing uses an up/down double arrow. Only positions exposed by your unit are offered. All functions uses the same control cards and mode selector as the dashboard.

The circular power control turns the unit on or off. Turning on applies the selected mode and its remembered configuration; explicit pending values override remembered ones. Each AC and mode has its own saved settings. Cool Night and Heat Night use cooling/heating with the unit's Sleep feature; selecting a standard mode disables Sleep when supported.

Target-temperature editors in All functions and preset forms use number wheels. Drag upward for a higher temperature or downward for a lower one; you can also scroll, click neighbouring values, or use the Up/Down keys. Home and End select the range limits. The wheel follows the AC's allowed step, including decimal steps, and stops at either end of its range. An unknown or unsupported current value stays unset until you choose one.

In the settings popup, **Set value** stages the selected temperature; **Apply changes** sends it to the AC. A preset's temperature remains a draft until you explicitly start the preset. The main dashboard keeps its temperature slider.

Animated airflow follows reported operation, with blue for cooling, amber for heating, and neutral for other modes. It stops when the unit is reported off. Pending edits do not change the animation before the AC reports its status.

## All functions

**Settings** contains ordinary adjustable controls. **Everyday use** contains comfort functions and presets. **Maintenance** contains cleaning and service functions. Options are discovered from the selected AC's hOn capabilities; unavailable or unreported values are identified in the interface.

**Silent mode** enables quieter AC operation. It was previously labelled **Quiet mode**. **Buzzer (Echo)** is the separate audible command-feedback setting, previously labelled **Voice / echo**; it is not voice-assistant control or Silent mode. Sleep remains a separate setting. These controls appear only when the selected AC exposes them as editable settings. Their selection cards explain the difference, and Search also finds these descriptions.

Use **Search** (or **Ctrl+F**) to find settings and presets across all three sections. Results stay grouped by their section, including maintenance. Search matches names, descriptions and option names; multiple words narrow the results. **Clear** or **Escape** returns to the current section. Selecting a section also clears the search. Search pauses while a preset's detail form is open; **Back to cards** restores your results.

Scroll anywhere inside the functions list, including the spaces between cards. The scrollbar appears only when the content exceeds the available height; shorter sections and search results stay fixed at the top. Numeric inputs in preset forms keep their own wheel behavior.

Select a preset to inspect its options, then explicitly start it. A preset may turn the AC on and replace its configuration. Maintenance routines can interrupt current operation. Saved program preferences never start cleaning or service routines automatically.

## On / off timers

**Start at** and **End at** are embedded directly below the temperature slider. Drag the hour or minute numbers up for later values, or down for earlier values; the wheel follows the pointer and snaps to the nearest number when released. You can also scroll, use the Up/Down keys, or click the neighbouring numbers. Click **Set** to save the next occurrence of that time, today or tomorrow, using your Windows local time zone. They are one-time controls only. A confirmed active schedule appears green with a **Stop** button inside its card; editing its time retains a separate Stop action.

Schedules are saved to **hOn's cloud service** and read back before success is displayed. You can switch the computer off after saving; the AC and router still need power and internet. This does not claim that a timer is stored physically inside the AC. Start at captures the selected mode, remembered configuration and pending edits, without applying them immediately. End at schedules a future power-off. Refresh also reads one-time timers created in hOn. You can change or stop a single supported timer from either app; if it changed since the last refresh, refresh again before editing it.

Stopping one half of a paired timer preserves the other half. Maintenance and recurring schedules are not exposed here. If several one-time schedules overlap or the cloud returns an unfamiliar format, the affected control becomes unavailable; manage those records in hOn. A failed or timed-out request may have reached the service: refresh and check hOn before retrying. There is no automatic retry of a timer mutation.

The previous PC scheduler is removed entirely, and old saved PC timers do not execute. Closing the application or signing out does not cancel cloud timers; use **Stop** explicitly. The offline preview uses fictional in-memory schedules and sends no requests. The cloud scheduling adapter was checked against hOn 2.30.7; future service changes may affect compatibility.

## Status and tray

Status updates through Cloud notifications with a check every 15 seconds as a backup. You can also use **Refresh**. Automatic updates preserve staged edits and open preset forms. Changes from the phone or physical remote appear once the AC reports them to the cloud. Temporary connection failures retry automatically.

Drag the integrated header to move the window, double-click to maximize/restore, or use its window controls. Minimize moves the app to the Windows notification area. Double-click the tray icon or choose **Open Room AC Control** to restore. **Exit** or the window's close button quits without turning the AC off.

The dashboard stays centred when resized. At its minimum size, timer cards and action buttons remain aligned, and timer controls retain their full height.

## Sign out and privacy

**Sign out** removes remembered credentials but retains your program preferences. Credentials and preferences are protected by Windows DPAPI in `%LOCALAPPDATA%\RoomACControl\state.dpapi`. They are separate from the application folder and are not part of a source upload or portable release.

For troubleshooting, use **Export diagnostics** on the login screen or **Diagnostics** in All functions. You choose the local JSON file; no report is automatically saved or uploaded. It contains the app version and up to 100 event times, event codes and error categories from this session. It excludes credentials, account/device names, identifiers and raw cloud responses. Review it before sharing. Report vulnerabilities through the [private security form](https://github.com/LuisBadal0/room-ac-control-hon/security/advisories/new).

Login, menus, inline timer previews and status refresh do not send AC control commands. An offline preview uses fictional rooms and never loads a saved account. If a command times out, refresh and check the physical unit before retrying: cloud acceptance does not guarantee that the unit has acted.
