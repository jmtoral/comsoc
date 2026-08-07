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
          "2023p"="Comsoc_Po_lizas_Transp_DICIEMBRE_2023_COM.xlsx",
          "2023d"="P_lizas_COMSOC_enero-diciembre_2023.xlsx")
out <- rbindlist(lapply(names(arch), function(yy){
  sk <- if (yy=="2023d") 6 else 5
  x <- suppressWarnings(as.data.table(read_excel(paste0(base,arch[[yy]]), sheet=1,
                                                 skip=sk, n_max=3000, col_types="text")))
  setnames(x, make.unique(names(x)))
  has <- "RFCB" %in% names(x)
  data.table(anio=yy, n_cols=ncol(x), tiene_RFCB=has,
             pct_RFCB_pobl = if(has) round(100*mean(!is.na(x$RFCB)),1) else NA_real_,
             ej_RFCB = if(has) na.omit(x$RFCB)[1] else NA_character_)
}))
print(out)
