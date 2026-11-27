# Changelog

What changes for people using Room AC Control, newest first. Each release on
GitHub uses its section from this file as its release notes.

Add a bullet under **Unreleased** in every pull request that changes what users
get. Releases are batched: a release pull request bumps the version, renames
**Unreleased** to that version and date, and starts a new, empty **Unreleased**
section above it.

## [Unreleased]

### Fixed

- An AC without a room temperature sensor no longer shows the room at 0° on the dashboard and in the tray, and no longer adds 0° readings to the room temperature history.
- A command the cloud service refuses no longer keeps the AC turning on or off quietly for the next three minutes: those notifications appear again.
- Timer messages now say what is wrong: a time in the past, or a time more than two days ahead. A repeating schedule whose time is skipped by the clock change now says so, instead of asking you to choose a day.
- After a check that finds no newer version, the Updates window no longer offers a release it found earlier.
- Closing the app hides the window at once instead of leaving it unresponsive for a few seconds while the cloud session closes.
- Signing in with several ACs no longer fails as "Could not reach the cloud service" when hOn is slow: each AC's timers and weather are read at the same time, signing in gets more time, and a slow sign-in says so.
- A change waiting behind a slow cloud request no longer waits without limit. After two minutes it stops with a message, and nothing is sent.
- Renewing the live-update connection every 30 minutes no longer holds up changes you apply at that moment.

## [0.11.0] - 2026-11-27

### Added

- **Self-clean countdown**, as in the hOn app's Maintenance screen. Each self-clean routine in **All functions › Maintenance** shows how many of its 30 days are left until the next clean is due, with a bar that turns amber at 10 days and red at 3. It counts from the last run, which now also includes the last self-clean date hOn keeps for your AC, or from when the AC was added to your account.

### Changed

- Turbo now runs on its own, as in the hOn app: turning Turbo on also turns off Silent mode and Sleep, and turning on Silent mode or Sleep, or choosing a different fan speed, turns Turbo off. A message on the dashboard says what changed, changing your mind before you apply puts the other switches back, and a mode's remembered settings never turn Turbo off by themselves. Nothing is sent until you apply.

## [0.10.1] - 2026-11-23

### Fixed

- The app's icon in the taskbar and title bar is sharp again instead of blurred.

## [0.10.0] - 2026-11-23

### Changed

- The tray icon's right-click menu now matches the app: light or dark with the app, a status card with the room temperature, mode and an on/off switch, an Eco switch, your top presets as buttons, and Exit. Left-click the icon to open the window.

## [0.9.0] - 2026-11-18

### Changed

- While an update installs, a small **Updating Room AC Control** window with a moving progress bar stays on screen until the new version opens, instead of the app simply disappearing for a few seconds.

## [0.8.1] - 2026-11-18

### Changed

- The image library bundled with the app (Pillow) is updated to 13.0.0, with the latest fixes.

## [0.8.0] - 2026-11-15

### Added

- **Room temperature history.** Select **Room** on the dashboard to see the room temperature over the last 24 hours or 7 days, with the lowest, average and highest values, the outside temperature and when the AC was on. hOn does not keep this history, so the app saves a reading every ten minutes while it is open (also from the notification area), encrypted on this computer, for seven days.
- **Energy use**, as in hOn's Energy consumption panel. The same sheet's **Energy** tab shows the kWh your AC reported to hOn this week, this month and this year, with a bar for each day or month. ACs that do not measure their consumption show that hOn has no energy data for them.
- **Windows notifications** while the app waits in the notification area: a new AC error code, a filter reminder, the AC going offline, and the AC turning on or off, saying when its timer did it. Changes you make in the app are not announced. Turn them off in **Settings › Notifications**.
- **Quick actions in the notification area.** Right-click the tray icon to see the AC's status and to turn it on or off, switch Eco or start one of your top presets without opening the window.

### Changed

- The sign-in screen now looks like the rest of the app: the unit picture with its airflow, rounded fields with icons, a **Remember me** switch, the same Sign in button, and messages inside the sign-in card instead of a strip at the bottom of the window.

## [0.7.0] - 2026-11-10

### Added

- **Outside** weather, as in the hOn app's **Outdoor** panel. When your AC does not measure humidity or air quality, the dashboard shows them for the location saved with the AC in hOn, marked with a small cloud; the outside temperature does the same when the AC has no outdoor sensor. Select one of these readings to see the temperature with the day's low and high, humidity, chance of rain, air quality, UV index, wind and air pressure.

### Changed

- Air quality now matches the hOn app: an AC that reports level 0 shows **Good** instead of "—" when no outside weather is available. A model without an air sensor also reports level 0, so Good on such a model is not a measurement.

### Fixed

- The app no longer stops responding after an unexpected error while showing a cloud result. Before, later results, the notification-area icon and update progress were ignored until the app was closed from Task Manager.
- Maintenance: when hOn's command history cannot be read, each routine shows the last run saved on this computer. Before, an error box opened and **Checking the last run…** never went away.
- Updates: when an update cannot be saved or unpacked on this computer, for example because the disk is full, the app says so. Before, it reported a problem reaching the update service.

## [0.6.0] - 2026-11-08

### Changed

- A copy installed with Setup.exe or the MSI now updates itself with the same signed installer. **Installed apps** in Windows shows the new version, and upgrades and uninstalling stay consistent. The new version is unpacked and checked before anything is installed, and Windows Installer keeps the previous version if the installation fails. Portable copies update as before.
- GitHub release notes now describe what changed for you, from this changelog.

### Fixed

- All functions opens again when the app runs from source on Python 3.11.
- After the app reconnects to cloud notifications, a late event from the old connection no longer triggers an extra status refresh.

## [0.5.1] - 2026-11-07

### Fixed

- Windows no longer go blank after about an hour of use. The image cache dropped images that were still on screen when it filled up; it now drops only images no window shows, and grows far more slowly.

## [0.5.0] - 2026-11-07

### Added

- Maintenance: select a routine's **Last run** line to set when it last ran (**Today**, **Yesterday** or a date), for runs the app did not see.
- Self-clean runs reported by the AC, including ones started in the hOn app or with the remote, now count as the routine's last run.

### Changed

- Runs more than 60 days ago show their date instead of a day count.
- All functions keeps the selected mode's colour while the AC is off.

## [0.4.1] - 2026-11-07

### Fixed

- Updates no longer fail silently when the app is open twice. Only one copy runs at a time; starting it again brings the open window to the front.
- If the app folder is in use during an update, the app says so and what to close.

### Added

- The main window shows update progress: download percentage, checking, then restarting.

## [0.4.0] - 2026-11-07

### Added

- Everyday use: choose up to four **Top presets**, in your own order, saved for each account and AC.
- Maintenance: each cleaning routine shows how long ago it last ran.

### Changed

- Heat presets show their target temperature in their settings, like Cool.

## [0.3.2] - 2026-11-06

### Changed

- The MSI installer shows the app's own artwork instead of the default WiX images.

## [0.3.1] - 2026-11-06

### Added

- Setup.exe and the MSI ask whether to create a desktop shortcut, and remember the choice on upgrades.

## [0.3.0] - 2026-11-06

### Added

- Every release includes a Setup.exe and an MSI installer, next to the portable ZIP. Both install for your Windows user only, without administrator rights.

## [0.2.4] - 2026-11-06

### Changed

- Starting a maintenance routine asks for confirmation in an in-app sheet instead of a Windows dialog.

## [0.2.3] - 2026-11-06

### Added

- A banner announces when a signed update is available, with **Update**.
- Presets can be saved with **Save** without starting them.

### Changed

- Settings keeps the selected mode's colour while the AC is off.
- A preset's airflow is chosen from louver drawings.
- Heat starts at 24° and Heat Night at 24° with Sleep and Silent mode, until you save your own values.

### Fixed

- The sign-in ring no longer drifts off its circle when the window resizes.

## [0.2.2] - 2026-11-06

### Changed

- The dashboard's **Airflow** tile opens the airflow picker.
- Dashboard controls light up under the pointer only while the AC is on.
- Maintenance routines have a **Start** button.
- Everyday use lists each favourite once and leaves out presets that repeat a mode.

## [0.2.1] - 2026-11-06

### Changed

- Everyday use shows Cool, Cool Night, Heat and Heat Night first, with their settings collapsed; other presets are under **More**.
- The dashboard always shows Room, Outside, Humidity and Air quality, with "—" for readings the AC does not report.

## [0.2.0] - 2026-11-06

### Changed

- A redesigned app: a temperature dial dashboard, a Settings dropdown in the window header and a new All functions window with Settings, Everyday use, Maintenance and Schedules.
- A new app icon, the bundled Manrope typeface and smooth, anti-aliased drawing.

## [0.1.24] - 2026-11-03

### Changed

- Updates moved to an icon in the main window header, with a dot when an update is waiting.

## [0.1.23] - 2026-11-03

### Added

- Signed in-app updates: the app checks GitHub about once a day and installs only after you click **Update**.

## [0.1.21] - 2026-11-03

### Fixed

- Schedules and All functions open without a white border.

## [0.1.18] - 2026-11-01

### Added

- Outside temperature, indoor humidity and air quality, when the AC reports them.

## [0.1.17] - 2026-10-27

### Changed

- Windows open at the size the layout was designed for and keep it.

## [0.1.16] - 2026-10-26

### Added

- Light and dark modes, with an **Appearance** setting that can follow Windows.

## Earlier 0.1 releases (0.1.0 to 0.1.15, 2026-10-12 to 2026-10-26)

### Added

- First releases: dashboard and All functions with search, cloud on/off timers saved in hOn, draggable time and temperature wheels, English and Portuguese, encrypted remembered sign-in, and a loading animation during sign-in.
