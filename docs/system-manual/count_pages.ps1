$w = New-Object -ComObject Word.Application
$w.Visible = $false
foreach ($f in @('_main.docx','_appendix.docx')) {
  $path = "E:\pipotsenvironmentallaw\pipotsenvironmentallaw\docs\system-manual\$f"
  try {
    $d = $w.Documents.Open($path, $false, $true)
    $pages = $d.ComputeStatistics(2)
    $words = $d.ComputeStatistics(0)
    Write-Output "$f pages=$pages words=$words"
    $d.Close($false)
  } catch {
    Write-Output "$f ERROR: $($_.Exception.Message)"
  }
}
$w.Quit()
