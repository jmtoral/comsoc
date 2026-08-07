suppressPackageStartupMessages({library(data.table)})
d <- fread("D:/Descargas/Publicidad Oficial/clean_data/clean_data.csv",
           encoding="UTF-8", showProgress=FALSE)
d[, yr := as.integer(substr(as.character(fecha_de_gasto),1,4))]
d <- d[yr >= 2012 & yr <= 2023]

cat("===== A) Renglones con costo NEGATIVO por año\n")
print(d[, .(n = .N,
            n_neg = sum(costo < 0, na.rm=TRUE),
            pct_neg = round(100*mean(costo < 0, na.rm=TRUE),2),
            monto_pos = round(sum(costo[costo>0], na.rm=TRUE)/1e6,1),
            monto_neg = round(sum(costo[costo<0], na.rm=TRUE)/1e6,1),
            pct_del_total = round(100*abs(sum(costo[costo<0],na.rm=TRUE))/sum(costo[costo>0],na.rm=TRUE),2)
            ), by=yr][order(yr)])

cat("\n===== B) ¿Cada negativo tiene su espejo positivo exacto en la MISMA póliza?\n")
k <- c("file_name","origin_sheet","entidad","poliza")
d[, absc := round(abs(costo),2)]
pares <- d[!is.na(costo) & costo != 0,
           .(pos = sum(costo>0), neg = sum(costo<0)),
           by = c(k,"absc","producto")]
cat("grupos (póliza+producto+|costo|) con al menos un negativo:", nrow(pares[neg>0]), "\n")
cat("  de ésos, con espejo positivo igual:", nrow(pares[neg>0 & pos>0]),
    sprintf("(%.1f%%)\n", 100*nrow(pares[neg>0 & pos>0])/max(1,nrow(pares[neg>0]))))
cat("  negativos SIN espejo exacto:", nrow(pares[neg>0 & pos==0]), "\n")

cat("\n===== C) Efecto de sumar vs. 'deduplicar' — total por año (millones)\n")
comp <- d[, .(
  suma_cruda      = round(sum(costo, na.rm=TRUE)/1e6,1),
  solo_positivos  = round(sum(costo[costo>0], na.rm=TRUE)/1e6,1)
), by=yr][order(yr)]
comp[, diferencia_pct := round(100*(solo_positivos-suma_cruda)/suma_cruda,2)]
print(comp)

cat("\n===== D) Filas exactamente duplicadas: ¿son error o renglones legítimos repetidos?\n")
cols <- setdiff(names(d), c("rowid","yr","absc"))
d[, dupkey := do.call(paste, c(.SD, sep="|")), .SDcols=cols]
dd <- d[, .N, by=dupkey][N>1]
cat("grupos de filas idénticas:", nrow(dd), " filas implicadas:", sum(dd$N), "\n")
cat("distribución del tamaño de grupo:\n"); print(table(pmin(dd$N,6)))
ej <- d[dupkey %in% dd[N==2]$dupkey][order(dupkey)][1:4]
print(ej[, .(yr, entidad, poliza, cons, producto, cantidad, costo, beneficiario=substr(beneficiario,1,25))])
