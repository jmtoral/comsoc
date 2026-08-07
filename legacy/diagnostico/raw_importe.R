suppressPackageStartupMessages({library(readxl); library(data.table)})
base <- "D:/Descargas/Publicidad Oficial/data/"

cat("########## 1) ¿La columna 'Importe' existe y está poblada en los archivos crudos?\n")
g1 <- c("2012"="Comsoc-12-Diciembre-2012_Definitivo.xlsx",
        "2015"="Comsoc-12-Diciembre-2015-Definitivo.xlsx",
        "2019"="Base_de_datos_Polizas_12_Diciembre-2019_Definitivo_Transp.xlsx",
        "2022"="Comsoc_Po_lizas_Transp_12_DICIEMBRE_2022.xlsx")
for (yy in names(g1)) {
  x <- read_excel(paste0(base, g1[[yy]]), sheet=1, skip=5, col_types="text")
  x <- as.data.table(x)
  setnames(x, make.unique(names(x)))
  ncol_x <- ncol(x)
  imp <- grep("^Importe", names(x), value=TRUE)[1]
  cos <- grep("^Costo$",  names(x), value=TRUE)[1]
  pol <- grep("^P.liza",  names(x), value=TRUE)[1]
  x <- x[!is.na(get(pol))]
  cat(sprintf("%s  ncols=%d  col_importe='%s'  filas=%d  %%NA importe=%.1f  %%NA costo=%.1f\n",
      yy, ncol_x, imp, nrow(x), 100*mean(is.na(x[[imp]])), 100*mean(is.na(x[[cos]]))))
  cat("     nombres:", paste(names(x), collapse=" | "), "\n")
}

cat("\n########## 2) Dentro de una póliza: Importe (nivel póliza) vs suma de Costo (nivel renglón)\n")
x <- as.data.table(read_excel(paste0(base,"Comsoc_Po_lizas_Transp_12_DICIEMBRE_2022.xlsx"),
                              sheet=1, skip=5))
setnames(x, make.unique(names(x)))
x <- x[!is.na(`Fecha de gasto`) & Mes != "Mes"]
x[, `:=`(imp=as.numeric(Importe), cst=as.numeric(Costo))]
h <- x[, .(n_renglones=.N, n_importes_distintos=uniqueN(round(imp,2)),
           importe=round(imp[1],2), suma_costo=round(sum(cst,na.rm=TRUE),2)),
       by=.(Entidad, `Póliza`)]
h[, ok := abs(importe-suma_costo) < 1]
cat("pólizas 2022 (hoja 3600):", nrow(h), "\n")
cat("  Importe constante dentro de la póliza:", round(100*mean(h$n_importes_distintos==1),1),"%\n")
cat("  Importe == suma(Costo) de sus renglones:", round(100*mean(h$ok, na.rm=TRUE),1),"%\n")
cat("\n  Pólizas con >1 renglón (aquí se ve la repetición del Importe):\n")
print(head(h[n_renglones>1][order(-n_renglones)], 6))
cat("\n  >> Si sumaras 'Importe' sobre TODOS los renglones:\n")
cat("     sum(Importe) por renglon =", round(sum(x$imp,na.rm=TRUE)/1e6,1), "M\n")
cat("     sum(Importe) 1 vez por póliza =", round(sum(h$importe,na.rm=TRUE)/1e6,1), "M\n")
cat("     sum(Costo)  por renglon =", round(sum(x$cst,na.rm=TRUE)/1e6,1), "M\n")

cat("\n########## 3) 2024 / 2025: valores de 'Tipo de Póliza' y montos negativos\n")
p24 <- as.data.table(read_excel(paste0(base,"Ejercido_P_lizasCOMSOC__Enero_a_diciembre_2024.xlsx"),
                                sheet=4, skip=8))
setnames(p24, make.unique(names(p24)))
p24 <- p24[!is.na(Sector)]
cat("2024 hoja 33605  filas=", nrow(p24), "\n"); print(table(p24[[grep("Tipo de P", names(p24))[1]]], useNA="ifany"))
mt <- grep("^Monto", names(p24), value=TRUE)[1]
cat("  negativos en", mt, ":", sum(as.numeric(p24[[mt]])<0, na.rm=TRUE), "\n")

p25 <- as.data.table(read_excel(paste0(base,"COMSOC_ejercido_enero-diciembre_2025.xlsx"),
                                sheet=4, skip=12))
setnames(p25, make.unique(names(p25)))
p25 <- p25[!is.na(Sector)]
cat("\n2025 hoja 36101-36201  filas=", nrow(p25), "\n")
print(table(p25[[grep("Tipo de P", names(p25))[1]]], useNA="ifany"))
mt5 <- grep("^Monto", names(p25), value=TRUE)[1]
cat("  negativos en", mt5, ":", sum(as.numeric(p25[[mt5]])<0, na.rm=TRUE), "\n")
cat("  suma Monto =", format(sum(as.numeric(p25[[mt5]]),na.rm=TRUE), big.mark=","),
    " (control del archivo: 3,702,598,799.12)\n")

cat("\n########## 4) 2025: filas exactamente duplicadas\n")
cols <- names(p25)
dupn <- sum(duplicated(p25, by=cols))
cat("  duplicados exactos 2025 (36101-36201):", dupn, "de", nrow(p25), "\n")
p25b <- p25[, .N, by=cols][N>1]
if(nrow(p25b)) print(head(p25b[order(-N)][, .(Mes=get(names(p25b)[5]), N)], 5))
