suppressPackageStartupMessages({library(data.table)})
setDTthreads(4)
d <- fread("D:/Descargas/Publicidad Oficial/clean_data/clean_data.csv",
           encoding = "UTF-8", showProgress = FALSE)
d[, yr := as.integer(substr(as.character(fecha_de_gasto), 1, 4))]
cat("filas totales:", nrow(d), "\n")
cat("años:", paste(sort(unique(d$yr)), collapse=","), "\n\n")

cat("===== 1) ¿Se usa 'importe/iva' (nivel póliza) o sólo 'costo'? % NA por año\n")
print(d[, .(n = .N,
            pct_importe_NA = round(100*mean(is.na(importe)),1),
            pct_costo_NA   = round(100*mean(is.na(costo)),1)), by = yr][order(yr)])

cat("\n===== 2) Filas por póliza  llave=(file_name, origin_sheet, entidad, poliza)\n")
g <- d[, .(n_filas = .N), by = .(file_name, origin_sheet, entidad, poliza)]
g[, yr := NULL]
d2 <- unique(d[, .(file_name, origin_sheet, entidad, poliza, yr)])
g <- merge(g, d2, by = c("file_name","origin_sheet","entidad","poliza"), allow.cartesian=TRUE)
print(dcast(g[, .N, by=.(yr, n_filas = pmin(n_filas, 6L))], yr ~ n_filas, value.var="N", fill=0))

cat("\n===== 3) Filas EXACTAMENTE duplicadas (todas las columnas salvo rowid)\n")
cols <- setdiff(names(d), c("rowid","yr"))
dup <- d[duplicated(d, by = cols)]
cat("duplicados exactos:", nrow(dup), "de", nrow(d), "\n")
if (nrow(dup)) print(dup[, .N, by = yr][order(yr)])

cat("\n===== 4) Valores de 'cons' (consecutivo) por año\n")
print(dcast(d[, .N, by = .(yr, cons = pmin(as.integer(cons), 4L))], yr ~ cons, value.var="N", fill=0))

cat("\n===== 5) Dentro de una póliza: ¿'importe' es constante y == suma de 'costo'?\n")
h <- d[!is.na(importe), .(n = .N,
                          n_importes_distintos = uniqueN(round(importe,2)),
                          importe1 = round(importe[1],2),
                          suma_costo = round(sum(costo, na.rm=TRUE),2)),
       by = .(file_name, origin_sheet, entidad, poliza)]
if (nrow(h)) {
  h[, coincide := abs(importe1 - suma_costo) < 1]
  cat("pólizas con importe no NA:", nrow(h), "\n")
  cat("  importe constante dentro de la póliza:", round(100*mean(h$n_importes_distintos==1),1), "%\n")
  cat("  importe == suma(costo):", round(100*mean(h$coincide),1), "%\n")
  print(head(h[coincide == FALSE][order(-n)], 5))
} else cat("  (importe siempre NA)\n")

cat("\n===== 6) Ejemplo: pólizas con exactamente 2 filas, ¿en qué difieren?\n")
g2 <- g[n_filas == 2]
set.seed(1)
smp <- g2[sample(.N, min(3, .N))]
for (i in seq_len(nrow(smp))) {
  r <- d[file_name==smp$file_name[i] & origin_sheet==smp$origin_sheet[i] &
         entidad==smp$entidad[i] & poliza==smp$poliza[i]]
  cat("\n--- póliza", smp$poliza[i], "|", smp$yr[i], "\n")
  print(r[, .(cons, producto, descripcion_producto, cantidad, costo_unitario, costo,
              iva_del_costo, beneficiario = substr(beneficiario,1,28))])
}
