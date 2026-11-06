# Using Room AC Control

Launch with **Start Room AC Control.cmd** or the local app-icon shortcut. Sign in using the hOn email/password account that already controls the AC on your phone. **Remember me on this computer** enables encrypted automatic sign-in after the first successful login.

Remember me is off by default. Enabling it saves your actual email and password using Windows encryption; other programs running as your Windows user can decrypt them. Existing remembered accounts retain their previous choice. Your password is passed to pyhOn for authentication.

During manual or automatic sign-in, a rotating loading ring appears while your account connects and AC settings load. The form returns if sign-in fails, so you can retry. Closing the application stops the animation.

## Choose a language

The interface starts in your Windows display language: English or Portuguese (Portugal). Other system languages use English as the fallback. Click **Settings** in the window header; its panel opens over the dashboard. Choose **System language**, **English**, or **Português (Portugal)** under **Language**. The choice takes effect immediately and is saved for later launches, including after signing out.

Changing language keeps your signed-in account, pending settings and open preset drafts. Account room names and model identifiers stay as supplied by hOn. Search accepts English and Portuguese labels, with or without accents. Portuguese shows decimal temperatures with a comma; command values sent to the service retain their original format. Unrecognized cloud labels remain in their original language.

## Choose light or dark

Click **Settings** in the main window header and choose **Follow Windows**, **Light mode** or **Dark mode** under **Appearance**. Follow Windows uses the app mode set in Windows Settings › Personalization › Colors and switches within a couple of seconds when you change it there. The choice applies immediately to every open window, keeps pending settings and drafts, and is saved for later launches.

## Select an AC

The room card shows the active AC's name and model. Accounts with several units have a **Switch** button: choose a room tile to load its status. A single unit displays its connection status directly. Room names come from your cloud account.

## Readings

Below the unit picture, one row shows the **Room** temperature and what the AC itself measures: **Outside** temperature (from the outdoor unit's sensor), indoor **Humidity** and **Air quality** (Good, Medium or Poor). A reading your model doesn't report shows —. Units without a sensor report 0, so a reading of exactly 0 also shows — rather than a real value. The outdoor sensor sits on the outdoor unit and can read warmer than the weather while the compressor runs in the sun.

A coloured banner below the unit picture appears when the AC reports a condition, and disappears by itself when it clears:

- **AC error** (red) with the code the unit reports. The code is shown as reported; check the unit or the troubleshooting section of the hOn app for its meaning.
- **Defrosting** (blue): in Heat mode the AC pauses heating to melt ice on the outdoor unit. This is normal and ends on its own.
- **Clean the air filter** (amber): the unit's filter reminder is on.

If several apply, the most serious is shown with a count such as **+1**.

## Set comfort controls

Set the temperature on the dial: drag along the ring, click a point on it, scroll over it, use the arrow keys, or use − and +. Choose a mode in the bar below the dial. Click the Fan speed tile to step to its next speed and the Sleep tile to turn Sleep on or off. The Airflow tile opens the same airflow picker as All functions, with every louver position drawn. Buttons light up under the pointer only while the AC is on. Changes are staged until you click **Apply**, which shows how many are waiting; **Discard** drops them. With nothing staged, the row says **In sync with the AC**. Other messages appear briefly above that row. Applying changes preserves the AC's power state.

The dashboard's accent follows the selected mode: blue for Cool, amber for Heat, green for Dry, violet for Fan and teal for Auto. The dial turns grey while the AC is off. Below the number, the dial says whether the AC is running, on standby, has changes pending or is awaiting confirmation.

Airflow position icons show the louver opening progressively: Position 1 is the most closed and Position 5 is the most open. Swing uses an up/down double arrow. Only positions exposed by your unit are offered. All functions uses the same control cards and mode selector as the dashboard.

The circular power control turns the unit on or off. Turning on applies the selected mode and its remembered configuration; explicit pending values override remembered ones. Each AC and mode has its own saved settings. Cool Night and Heat Night use cooling/heating with the unit's Sleep feature: choose Cool or Heat, then turn on Sleep. Selecting a mode in the mode bar turns Sleep off when supported.

Target-temperature editors in All functions and preset forms use number wheels. Drag upward for a higher temperature or downward for a lower one; you can also scroll, click neighbouring values, or use the Up/Down keys. Home and End select the range limits. The wheel follows the AC's allowed step, including decimal steps, and stops at either end of its range. An unknown or unsupported current value stays unset until you choose one.

In the settings popup, **Set value** stages the selected temperature; **Apply changes** sends it to the AC. A preset's temperature remains a draft until you explicitly start the preset. The main dashboard keeps its temperature dial.

Animated airflow follows reported operation, with blue for cooling, amber for heating, and neutral for other modes. It stops when the unit is reported off. Pending edits do not change the animation before the AC reports its status.

## All functions

All functions has four tabs. Options are discovered from the selected AC's hOn capabilities; unavailable or unreported values are identified in the interface. Choices you make here are staged on the dashboard: **Apply** and **Discard** appear at the bottom while changes wait, and the dashboard shows the same count.

- **Settings**: a Comfort card with every mode, the fan speeds, airflow (which opens a picker that draws each louver position) and the target temperature; **Features** tiles that switch on/off settings such as Eco, Silent mode, Sleep and Buzzer (Echo); and **More settings** for anything else your AC exposes.
- **Everyday use**: Cool, Cool Night, Heat and Heat Night first, each with its settings (mode, temperature, fan, airflow and features) behind **Show settings**; any other presets under **More**, closed until you open it (presets that only repeat a mode from the mode bar are left out); and **Remembered per mode**, showing what each mode brings back when the AC is turned on in it.
- **Maintenance**: the air-filter reminder status and the cleaning routines your AC offers. **Start** (or **Turn on**) asks you to confirm, then sends the routine; the card then shows **Started**.
- **Schedules**: a week view of every timer saved in hOn, the repeating schedules with their days, mode and an on/off switch, one-time timers, and **New schedule** (see Repeating schedules).

**Silent mode** enables quieter AC operation. It was previously labelled **Quiet mode**. **Buzzer (Echo)** is the separate audible command-feedback setting, previously labelled **Voice / echo**; it is not voice-assistant control or Silent mode. Sleep remains a separate setting. These controls appear only when the selected AC exposes them as editable settings. Their selection cards explain the difference, and Search also finds these descriptions.

Use **Search** (or **Ctrl+F**) to find settings and presets across Settings, Everyday use and Maintenance. Results stay grouped by their section. Search matches names, descriptions and option names; multiple words narrow the results. **Escape** returns to the current tab, and selecting a tab also clears the search. Search pauses while a preset is open; **Back to cards** restores your results.

Scroll anywhere inside the list, including the spaces between cards. Shorter tabs and search results stay fixed at the top. The temperature wheel in a preset keeps its own wheel behaviour.

Select a preset to review it in a sheet at the bottom of the window, adjust its temperature, fan, airflow and features, then explicitly start it. A preset may turn the AC on and replace its configuration. Maintenance routines can interrupt current operation. Saved program preferences never start cleaning or service routines automatically.

## On / off timers

**End at** sits at the bottom of the dashboard. Drag the hour or minute numbers up for later values, or down for earlier values; the wheel follows the pointer and snaps to the nearest number when released. You can also scroll, use the Up/Down keys, or click the neighbouring numbers. Click **Set** to save the next occurrence of that time, today or tomorrow, using your Windows local time zone. The chip beside the wheels says **Once**; select it to repeat instead (see below). A confirmed active timer turns the row blue with a **Stop** button; editing its time retains a separate Stop action. To turn the AC on at a time, add a schedule in **Schedules**.

Schedules are saved to **hOn's cloud service** and read back before success is displayed. You can switch the computer off after saving; the AC and router still need power and internet. This does not claim that a timer is stored physically inside the AC. A scheduled start uses the selected mode and its remembered configuration, without applying them immediately. End at schedules a future power-off. Refresh also reads one-time timers created in hOn. You can change or stop a single supported timer from either app; if it changed since the last refresh, refresh again before editing it.

Stopping one half of a paired timer preserves the other half. Maintenance routines are not exposed here. If several one-time schedules overlap or the cloud returns an unfamiliar format, the affected card becomes unavailable; delete the extra ones in **Schedules** or in hOn. A failed or timed-out request may have reached the service: refresh and check hOn before retrying. There is no automatic retry of a timer mutation.

## Repeating schedules

Select the **Once** chip on End at and choose **Every day**, **Weekdays**, **Weekend** or **Choose days…**. The chip turns blue and **Set** then saves a repeating schedule instead of a one-time timer; the row returns to Once afterwards. A schedule that turns the AC on uses the selected mode with its remembered settings.

**Schedules**, the last tab in All functions, lists every timer saved in hOn for the selected AC, including ones made in the phone app:

- Repeating schedules show their times, days and the mode and temperature they apply. Use the switch to pause or resume one without deleting it, **Edit** to change its times, days, mode or temperature, or **Delete** to remove it.
- Upcoming one-time timers are listed with their date and can be deleted.
- Monthly or other repeats created in hOn are listed as **Manage in hOn**.

**New schedule** opens the editor: tick **Turn on at**, **Turn off at** or both, choose the days, and pick the mode and temperature used when it turns on; fan, airflow and other settings follow what you last used in that mode. If another active schedule starts or ends at the same time on one of the same days, you are asked before it is saved.

Repeating schedules are written in the same format the hOn app uses (days Monday to Sunday, repeated every day or weekly) and read back before success is shown. They run in hOn's cloud with the PC off, show in the phone app, and keep the clock time they were saved with: after a daylight-saving change, edit and save them again if the time looks an hour off.

The previous PC scheduler is removed entirely, and old saved PC timers do not execute. Closing the application or signing out does not cancel cloud timers; use **Stop** explicitly. The offline preview uses fictional in-memory schedules and sends no requests. The cloud scheduling adapter was checked against hOn 2.30.7; future service changes may affect compatibility.

## Status and tray

Status updates through Cloud notifications with a check every 15 seconds as a backup. You can also use **↻** (Refresh) beside All functions. Automatic updates preserve staged edits and open preset forms. Changes from the phone or physical remote appear once the AC reports them to the cloud. Temporary connection failures retry automatically.

After an accepted settings command, **Awaiting confirmation** keeps the values you sent visible while the cloud still reports older values. These are separate from unsent changes and are not automatically resent. Matching reports confirm them; after 60 seconds without confirmation, the next successful refresh shows the reported values with a warning. The power indicator and airflow animation continue to follow reported operation.

Drag the integrated header to move the window, or use its minimize and close controls. Minimize moves the app to the Windows notification area. Double-click the tray icon or choose **Open Room AC Control** to restore. **Exit** or the window's close button quits without turning the AC off.

The main window and All functions open at a fixed size designed for their layout, so they cannot be resized or maximized. All functions scrolls when a section has more cards than fit.

## Updates

The portable app checks for a newer version shortly after it starts and then about once a day. **Settings** in the main window header shows the installed version and the update status (for example **Last checked today at 09:12**), with **Check now**, or **Update** when a new version is available; the button shows a dot when a new version is waiting. Click the version line to open the Updates window with **What's new** and **Diagnostics**.

Nothing is installed until you click **Update**. Room AC Control then downloads the new version and checks that it is signed by this project and matches its published fingerprint. It unpacks the new version next to the current one and runs its offline checks. Only when all of that passes does the app close, swap the folders and open the new version, usually within a few seconds. If the swap fails, the previous version is put back and the app tells you on its next start. Your remembered sign-in, settings and schedules are kept because they live in your Windows profile, not in the app folder. Unapplied changes are discarded, and the app asks before discarding them.

Turn off **Check automatically** in Settings (or **Check for updates automatically** in the Updates window) to stop the daily checks; **Check now** still works. Source checkouts and the offline preview never check or install updates. If the app folder is not writable (for example, under Program Files), download the new release from GitHub instead.

## Sign out and privacy

**Sign out**, at the bottom of **Settings**, removes remembered credentials but retains your program preferences. Credentials and preferences are protected by Windows DPAPI in `%LOCALAPPDATA%\RoomACControl\state.dpapi`. They are separate from the application folder and are not part of a source upload or portable release.

For troubleshooting, use **Export diagnostics** on the login screen or **Diagnostics** in the Updates window (click the version line in Settings). You choose the local JSON file; no report is automatically saved or uploaded. It contains the app version and up to 100 event times, event codes and error categories from this session. It excludes credentials, account/device names, identifiers and raw cloud responses. Review it before sharing. Report vulnerabilities through the [private security form](https://github.com/LuisBadal0/room-ac-control-hon/security/advisories/new).

Login, menus, inline timer previews and status refresh do not send AC control commands. An offline preview uses fictional rooms and never loads a saved account. If a command times out, refresh and check the physical unit before retrying: cloud acceptance does not guarantee that the unit has acted.
