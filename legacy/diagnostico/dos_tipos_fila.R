suppressPackageStartupMessages({library(readxl); library(data.table)})
base <- "D:/Descargas/Publicidad Oficial/data/"
arch <- c("2012"="Comsoc-12-Diciembre-2012_Definitivo.xlsx",
          "2013"="comsoc_12_diciembre_2013_definitivo.xlsx",
          "2014"="comsoc-12-dic-2014-definitivo.xlsx",
          "2015"="Comsoc-12-Diciembre-2015-Definitivo.xlsx",
          "2016"="ComsocPólizas12Dic-2016Defin.xlsx",
          "2017"="Comsoc Pólizas 12 Defin_Diciembre-2017 Transp VF.xlsx",
          "2018"="Comsoc_Pólizas_Transp 12_Diciembre-2018_Defin.xlsx",
          "2019"="Base_de_datos_Polizas_12_Diciembre-2019_Definitivo_Transp.xlsx",
          "2020"="Comsoc_P_lizas_12_Diciembre_2020_Trnsp_Def.xlsx",
          "2021"="Comsoc_Po_lizas_Trans_12_Diciembre_2021.xlsx",
          "2022"="Comsoc_Po_lizas_Transp_12_DICIEMBRE_2022.xlsx",
          "2023d"="P_lizas_COMSOC_enero-diciembre_2023.xlsx")

res <- rbindlist(lapply(names(arch), function(yy) {
  sk <- if (yy == "2023d") 6 else 5
  rbindlist(lapply(1:2, function(sh) {
    x <- suppressWarnings(as.data.table(
          read_excel(paste0(base, arch[[yy]]), sheet=sh, skip=sk, col_types="text")))
    setnames(x, make.unique(names(x)))
    fg <- grep("^Fecha de gasto$", names(x), ignore.case=TRUE, value=TRUE)[1]
    x <- x[!is.na(get(fg)) & (is.na(Mes) | Mes != "Mes")]
    num <- function(v) suppressWarnings(as.numeric(gsub("[^0-9.-]", "", v)))
    imp <- num(x[["Importe"]]); cst <- num(x[["Costo"]]); cant <- num(x[["Cantidad"]])
    data.table(anio=yy, hoja=sh, filas=nrow(x),
      filas_con_Importe = sum(!is.na(imp)),
      filas_con_Costo   = sum(!is.na(cst)),
      filas_con_AMBOS   = sum(!is.na(imp) & !is.na(cst)),
      filas_con_NINGUNO = sum(is.na(imp) & is.na(cst)),
      Cantidad_NA_en_filas_Importe = sum(!is.na(imp) & is.na(cant)),
      suma_Importe_M = round(sum(imp, na.rm=TRUE)/1e6, 1),
      suma_Costo_M   = round(sum(cst, na.rm=TRUE)/1e6, 1))
  }))
}))
res[, `:=`(pct_ambos = round(100*filas_con_AMBOS/filas, 2),
           dif_pct   = round(100*(suma_Importe_M-suma_Costo_M)/suma_Costo_M, 2))]

cat("===== Estructura de filas por archivo/hoja (hoja1=3600, hoja2=33605)\n")
print(res[, .(anio, hoja, filas, con_Importe=filas_con_Importe, con_Costo=filas_con_Costo,
              AMBOS=filas_con_AMBOS, pct_ambos, Cant_NA_si_Importe=Cantidad_NA_en_filas_Importe)])

cat("\n===== ¿Importe y Costo miden lo mismo? (millones de pesos, por hoja)\n")
print(res[, .(anio, hoja, suma_Importe_M, suma_Costo_M, dif_pct)])

cat("\n===== TOTAL por año (ambas hojas)\n")
tot <- res[, .(suma_Importe_M=sum(suma_Importe_M), suma_Costo_M=sum(suma_Costo_M),
               filas_Importe=sum(filas_con_Importe), filas_Costo=sum(filas_con_Costo)), by=anio]
tot[, dif_pct := round(100*(suma_Importe_M-suma_Costo_M)/suma_Costo_M, 2)]
print(tot)
