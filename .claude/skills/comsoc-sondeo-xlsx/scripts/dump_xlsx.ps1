Add-Type -AssemblyName System.IO.Compression.FileSystem
function Dump-Xlsx {
  param([string]$Path,[int]$MaxRows=8)
  $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
  function ReadEntry($name){
    $e = $zip.Entries | Where-Object { $_.FullName -eq $name }
    if(-not $e){ return $null }
    $sr = New-Object System.IO.StreamReader($e.Open(), [System.Text.Encoding]::UTF8)
    $t = $sr.ReadToEnd(); $sr.Close(); return $t
  }
  # shared strings
  $ss = @()
  $sst = ReadEntry 'xl/sharedStrings.xml'
  if($sst){
    $x = [xml]$sst
    foreach($si in $x.sst.si){
      if($si.t -is [string]){ $ss += $si.t }
      elseif($si.t.'#text'){ $ss += $si.t.'#text' }
      elseif($si.r){ $ss += (($si.r | ForEach-Object { if($_.t -is [string]){$_.t} else {$_.t.'#text'} }) -join '') }
      else { $ss += '' }
    }
  }
  $wb = [xml](ReadEntry 'xl/workbook.xml')
  $rels = [xml](ReadEntry 'xl/_rels/workbook.xml.rels')
  $i = 0
  foreach($sheet in $wb.workbook.sheets.sheet){
    $i++
    $rid = $sheet.id
    if(-not $rid){ $rid = $sheet.GetAttribute('id','http://schemas.openxmlformats.org/officeDocument/2006/relationships') }
    $target = ($rels.Relationships.Relationship | Where-Object { $_.Id -eq $rid }).Target
    $target = $target -replace '^/xl/',''
    $entryName = "xl/$target"
    Write-Output ("--- HOJA {0}: {1}  [{2}]" -f $i, $sheet.name, $entryName)
    $sx = ReadEntry $entryName
    if(-not $sx){ Write-Output "    (no encontrada)"; continue }
    $doc = [xml]$sx
    $r = 0
    foreach($row in $doc.worksheet.sheetData.row){
      $r++
      if($r -gt $MaxRows){ break }
      $vals = @()
      foreach($c in $row.c){
        $ref = $c.r
        $v = $c.v
        if($c.t -eq 's' -and $v -ne $null){ $v = $ss[[int]$v] }
        elseif($c.t -eq 'inlineStr'){ $v = $c.is.t }
        if($v -ne $null -and "$v".Trim() -ne ''){ $vals += ("{0}={1}" -f $ref, ("$v" -replace '\s+',' ')) }
      }
      if($vals.Count -gt 0){ Write-Output ("  r{0}: {1}" -f $row.r, ($vals -join ' | ')) }
    }
  }
  $zip.Dispose()
}
