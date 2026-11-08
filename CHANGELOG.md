# Changelog

What changes for people using Room AC Control, newest first. Each release on
GitHub uses its section from this file as its release notes.

Add a bullet under **Unreleased** in every pull request that changes what users
get. Releases are batched: a release pull request bumps the version, renames
**Unreleased** to that version and date, and starts a new, empty **Unreleased**
section above it.

## [Unreleased]

## [0.6.0] - 2026-11-08

### Changed

- A copy installed with Setup.exe or the MSI now updates itself with the same signed installer. **Installed apps** in Windows shows the new version, and upgrades and uninstalling stay consistent. The new version is unpacked and checked before anything is installed, and Windows Installer keeps the previous version if the installation fails. Portable copies update as before.

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
