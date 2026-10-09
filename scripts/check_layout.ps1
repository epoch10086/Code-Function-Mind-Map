param(
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$SheetTitle = 'api',
    [string]$Preview = ''
)
# Measures generated topic text using the Windows font. This is a geometry
# preview, not XMind native-client rendering or an open/save/reopen test.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.IO.Compression.FileSystem
$mapOutput = (Resolve-Path -LiteralPath $Output).Path
$nav = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $mapOutput 'auxiliary/data/navigation-index.json') | ConvertFrom-Json
$archive = [IO.Compression.ZipFile]::OpenRead((Join-Path $mapOutput 'code-function-call-mindmap.xmind'))
try {
    $reader = New-Object IO.StreamReader($archive.GetEntry('content.json').Open(),[Text.Encoding]::UTF8)
    try { $sheets = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
} finally { $archive.Dispose() }
$canvas = New-Object Drawing.Bitmap(1800,1400)
$canvas.SetResolution(96,96)
$drawing = [Drawing.Graphics]::FromImage($canvas)
$drawing.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
$drawing.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$drawing.Clear([Drawing.Color]::White)
$format = [Drawing.StringFormat]::GenericTypographic.Clone()
$format.Alignment = [Drawing.StringAlignment]::Center
$format.LineAlignment = [Drawing.StringAlignment]::Center
$format.FormatFlags = [Drawing.StringFormatFlags]::NoWrap
$overflows = @()
$measured = 0
$selected = $sheets | Where-Object { $_.title -like ('*'+$SheetTitle+'*') } | Select-Object -First 1
if ($null -eq $selected) { $selected = $sheets[1] }
try {
    foreach ($sheet in $sheets) {
        foreach ($topic in @($sheet.rootTopic) + @($sheet.rootTopic.children.detached)) {
            $box = $nav.geometry.($topic.id)
            $fontSize = [float]($topic.style.properties.'fo:font-size' -replace 'pt$','')
            $font = New-Object Drawing.Font('Microsoft YaHei',$fontSize,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Point)
            try {
                $size = $drawing.MeasureString([string]$topic.title,$font,10000,$format)
                $measured++
                if ($size.Width -gt ($box.width - 12) -or $size.Height -gt ($box.height - 8)) {
                    $overflows += [pscustomobject]@{ sheet=$sheet.title; topic=$topic.title; width=$size.Width; height=$size.Height; cardWidth=$box.width; cardHeight=$box.height }
                }
                if ($sheet.id -eq $selected.id) {
                    $rect = New-Object Drawing.RectangleF([float]($box.x-$box.width/2+900),[float]($box.y-$box.height/2+100),[float]$box.width,[float]$box.height)
                    $brush = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml($topic.style.properties.'svg:fill'))
                    try {
                        $drawing.FillRectangle($brush,$rect)
                        $drawing.DrawRectangle([Drawing.Pens]::LightSlateGray,$rect.X,$rect.Y,$rect.Width,$rect.Height)
                        $drawing.DrawString([string]$topic.title,$font,[Drawing.Brushes]::DarkSlateGray,$rect,$format)
                    } finally { $brush.Dispose() }
                }
            } finally { $font.Dispose() }
        }
    }
    if ($Preview) { $canvas.Save([IO.Path]::GetFullPath($Preview),[Drawing.Imaging.ImageFormat]::Png) }
} finally { $format.Dispose();$drawing.Dispose();$canvas.Dispose() }
[pscustomobject]@{ topics_measured=$measured; font='Microsoft YaHei at 96dpi'; overflows=$overflows; preview_sheet=$selected.title; native_app_check='not_run' } | ConvertTo-Json -Depth 5
if ($overflows.Count) { exit 1 }
