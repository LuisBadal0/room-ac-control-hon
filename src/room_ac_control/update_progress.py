"""A small "Updating…" window shown while the app is closed for an update.

The app exits before the helper swaps folders or runs the installer, so nothing
of Room AC Control can stay on screen. Windows PowerShell (part of every
Windows 10 and 11) shows this window instead: it starts from the updates folder,
so it never holds a file in the app folder open, and it closes once the new
version has opened its window, the helper has stopped, or after a time limit.
"""

import os
import shutil
import subprocess
from pathlib import Path

from .update_install import updates_folder
from .update_release import NO_WINDOW

# The script is static ASCII. Text and colours reach it only through environment
# variables, so translated text and any folder name are safe. It needs no
# compiled code and no administrator rights.
SCRIPT = r"""$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

function Setting([string]$name, [string]$fallback) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrEmpty($value)) { return $fallback }
    return $value
}

function Paint([string]$name, [string]$fallback) {
    $text = Setting $name $fallback
    try { return [System.Windows.Media.BrushConverter]::new().ConvertFromString($text) }
    catch { return [System.Windows.Media.BrushConverter]::new().ConvertFromString($fallback) }
}

$card = Paint 'UPDATE_COLOR_CARD' '#FFFFFF'
$edge = Paint 'UPDATE_COLOR_EDGE' '#DDE2E9'
$text = Paint 'UPDATE_COLOR_TEXT' '#12161C'
$muted = Paint 'UPDATE_COLOR_MUTED' '#556070'
$track = Paint 'UPDATE_COLOR_TRACK' '#E3E8EE'
$brand = Paint 'UPDATE_COLOR_BRAND' '#0A6CA5'
$result = Setting 'UPDATE_RESULT' ''
$app = [IO.Path]::GetFileNameWithoutExtension((Setting 'UPDATE_EXECUTABLE' 'RoomACControl.exe'))
$helper = 0
[void][int]::TryParse((Setting 'UPDATE_HELPER_PID' '0'), [ref]$helper)

$window = New-Object System.Windows.Window
$window.Title = 'Room AC Control'
$window.WindowStyle = 'None'
$window.AllowsTransparency = $true
$window.Background = [System.Windows.Media.Brushes]::Transparent
$window.ResizeMode = 'NoResize'
$window.SizeToContent = 'Height'
$window.Width = 432
$window.WindowStartupLocation = 'CenterScreen'
$window.Topmost = $true
$window.ShowActivated = $true
$window.FontFamily = New-Object System.Windows.Media.FontFamily 'Segoe UI'

$frame = New-Object System.Windows.Controls.Border
$frame.Margin = New-Object System.Windows.Thickness 16
$frame.Padding = New-Object System.Windows.Thickness 24, 22, 24, 24
$frame.CornerRadius = New-Object System.Windows.CornerRadius 14
$frame.Background = $card
$frame.BorderBrush = $edge
$frame.BorderThickness = New-Object System.Windows.Thickness 1
$shadow = New-Object System.Windows.Media.Effects.DropShadowEffect
$shadow.BlurRadius = 18
$shadow.ShadowDepth = 3
$shadow.Opacity = 0.25
$frame.Effect = $shadow
$window.Content = $frame

$stack = New-Object System.Windows.Controls.StackPanel
$frame.Child = $stack

$top = New-Object System.Windows.Controls.DockPanel
$top.LastChildFill = $true
$stack.Children.Add($top) | Out-Null
$iconPath = Setting 'UPDATE_ICON' ''
if ($iconPath -and (Test-Path -LiteralPath $iconPath)) {
    try {
        $bitmap = New-Object System.Windows.Media.Imaging.BitmapImage
        $bitmap.BeginInit()
        $bitmap.CacheOption = 'OnLoad'
        $bitmap.UriSource = New-Object System.Uri $iconPath
        $bitmap.EndInit()
        $image = New-Object System.Windows.Controls.Image
        $image.Source = $bitmap
        $image.Width = 44
        $image.Height = 44
        $image.Margin = New-Object System.Windows.Thickness 0, 0, 14, 0
        [System.Windows.Controls.DockPanel]::SetDock($image, 'Left')
        $top.Children.Add($image) | Out-Null
    } catch { }
}
$heading = New-Object System.Windows.Controls.StackPanel
$heading.VerticalAlignment = 'Center'
$top.Children.Add($heading) | Out-Null
$title = New-Object System.Windows.Controls.TextBlock
$title.Text = Setting 'UPDATE_TITLE' 'Updating Room AC Control'
$title.FontSize = 17
$title.FontWeight = 'SemiBold'
$title.Foreground = $text
$title.TextWrapping = 'Wrap'
$heading.Children.Add($title) | Out-Null
$version = New-Object System.Windows.Controls.TextBlock
$version.Text = Setting 'UPDATE_VERSION_TEXT' ''
$version.FontSize = 12.5
$version.Foreground = $muted
$version.Margin = New-Object System.Windows.Thickness 0, 2, 0, 0
$heading.Children.Add($version) | Out-Null

$detail = New-Object System.Windows.Controls.TextBlock
$detail.Text = Setting 'UPDATE_DETAIL' 'Room AC Control opens again when the update is done.'
$detail.FontSize = 13
$detail.Foreground = $muted
$detail.TextWrapping = 'Wrap'
$detail.Margin = New-Object System.Windows.Thickness 0, 18, 0, 16
$stack.Children.Add($detail) | Out-Null

$bar = New-Object System.Windows.Controls.Border
$bar.Height = 6
$bar.CornerRadius = New-Object System.Windows.CornerRadius 3
$bar.Background = $track
$bar.ClipToBounds = $true
$stack.Children.Add($bar) | Out-Null
$canvas = New-Object System.Windows.Controls.Canvas
$bar.Child = $canvas
$runner = New-Object System.Windows.Controls.Border
$runner.Width = 110
$runner.Height = 6
$runner.CornerRadius = New-Object System.Windows.CornerRadius 3
$runner.Background = $brand
$canvas.Children.Add($runner) | Out-Null
$move = New-Object System.Windows.Media.TranslateTransform
$runner.RenderTransform = $move
$slide = New-Object System.Windows.Media.Animation.DoubleAnimation
$slide.From = -110
$slide.To = 400
$slide.Duration = New-Object System.Windows.Duration ([TimeSpan]::FromSeconds(1.4))
$slide.RepeatBehavior = [System.Windows.Media.Animation.RepeatBehavior]::Forever
$ease = New-Object System.Windows.Media.Animation.SineEase
$ease.EasingMode = 'EaseInOut'
$slide.EasingFunction = $ease
$move.BeginAnimation([System.Windows.Media.TranslateTransform]::XProperty, $slide)

$window.Add_MouseLeftButtonDown({ try { $window.DragMove() } catch { } })
$window.Add_KeyDown({ if ($_.Key -eq 'Escape') { $window.Close() } })

# True when the new version has opened its window.
function Opened { $null -ne (Get-Process -Name $app -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }) }

$started = Get-Date
$script:opening = $null
$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(400)
$timer.Add_Tick({
    $now = Get-Date
    if ($null -eq $script:opening) {
        $done = $result -and (Test-Path -LiteralPath $result)
        if ($done) {
            # The helper gave up waiting for the old app and opens nothing.
            $outcome = Get-Content -LiteralPath $result -Raw -ErrorAction SilentlyContinue
            if ($outcome -match '"timeout"') { $window.Close(); return }
        }
        $running = $helper -gt 0 -and $null -ne (Get-Process -Id $helper -ErrorAction SilentlyContinue)
        # A helper that already finished means the new version is starting, or has
        # started and removed the result file.
        if ($done -or -not $running) {
            if (Opened) { $window.Close(); return }
            $script:opening = $now
            $detail.Text = Setting 'UPDATE_OPENING' 'Opening Room AC Control...'
            return
        }
        if (($now - $started).TotalMinutes -gt 20) { $window.Close() }
        return
    }
    if ((Opened) -or ($now - $script:opening).TotalSeconds -gt 20) { $window.Close() }
})
$timer.Start()
$window.ShowDialog() | Out-Null
"""


def powershell():
    root = os.environ.get("SystemRoot", r"C:\Windows")
    path = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(path) if path.is_file() else "powershell.exe"


def launch_progress(version, helper_pid, texts, colors, folder=None, icon=None, popen=subprocess.Popen):
    """Show the "Updating…" window until the new version opens.

    `texts` holds the translated title, version line (the plain version when
    missing), detail and opening text;
    `colors` holds hex colours for CARD, EDGE, TEXT, MUTED, TRACK and BRAND."""
    folder = folder or updates_folder()
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "update-progress.ps1"
    script.write_text(SCRIPT.replace("\n", "\r\n"), encoding="ascii", newline="")
    picture = None
    if icon is not None:
        # A copy, so the window never holds a file in the app folder that the update replaces.
        try:
            picture = folder / "update-icon.png"
            shutil.copyfile(icon, picture)
        except OSError:
            picture = None
    environment = {
        **os.environ,
        "UPDATE_RESULT": str(folder / "result.json"),
        "UPDATE_HELPER_PID": str(helper_pid),
        "UPDATE_EXECUTABLE": "RoomACControl.exe",
        "UPDATE_ICON": str(picture or ""),
        "UPDATE_TITLE": texts["title"],
        "UPDATE_VERSION_TEXT": texts.get("version", version),
        "UPDATE_DETAIL": texts["detail"],
        "UPDATE_OPENING": texts["opening"],
        **{f"UPDATE_COLOR_{name}": value for name, value in colors.items()},
    }
    flags = NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return popen(
        [
            powershell(),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Sta",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(folder),
        env=environment,
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
