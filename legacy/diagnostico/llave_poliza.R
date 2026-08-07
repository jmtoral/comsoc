suppressPackageStartupMessages({library(data.table); library(readxl)})
d <- fread("D:/Descargas/Publicidad Oficial/legacy/clean_data/clean_data.csv",
           encoding="UTF-8", showProgress=FALSE)
d[, yr := as.integer(substr(as.character(fecha_de_gasto),1,4))]
d <- d[yr >= 2012 & yr <= 2023 & !is.na(costo)]
d[, grupo := fifelse(grepl("33605", origin_sheet), "33605", "36101-36201")]
d[, anio := as.integer(sub(".*?((19|20)\\d{2}).*", "\\1", file_name))]
d[, ent := sprintf("%05d", suppressWarnings(as.integer(entidad)))]

cat("===== 1) ¿Una póliza abarca más de una PARTIDA? (36101 vs 36201)\n")
g <- d[grupo=="36101-36201", .(n_partidas=uniqueN(partida)), by=.(anio, ent, poliza)]
print(table(g$n_partidas))
cat("  -> si hay >1, la llave NO debe incluir 'partida' sino 'partida_grupo'\n")

cat("\n===== 2) ¿El mismo numero de poliza aparece en los DOS grupos de partida?\n")
g2 <- d[, .(n_grupos=uniqueN(grupo)), by=.(anio, ent, poliza)]
cat("  pólizas en ambos grupos:", sum(g2$n_grupos>1), "de", nrow(g2), "\n")

cat("\n===== 3) ¿El mismo numero de poliza se repite entre ENTIDADES el mismo año?\n")
g3 <- d[, .(n_ent=uniqueN(ent)), by=.(anio, grupo, poliza)]
cat("  números de póliza usados por >1 entidad:", sum(g3$n_ent>1), "de", nrow(g3), "\n")
cat("  -> confirma que 'clave_entidad' es indispensable en la llave\n")

cat("\n===== 4) Renglones por poliza con la llave propuesta (anio, grupo, ent, poliza)\n")
g4 <- d[, .N, by=.(anio, grupo, ent, poliza)]
cat("  pólizas distintas:", nrow(g4), " renglones:", sum(g4$N), "\n")
print(summary(g4$N))
print(table(pmin(g4$N, 8)))

cat("\n===== 5) 2023: ¿la misma poliza existe en preliminar y definitiva?\n")
p <- d[anio==2023]
cat("  archivos 2023 en clean_data:", paste(unique(p$file_name), collapse=" | "), "\n")

cat("\n===== 6) 2024/2025: ¿existe columna Poliza y se repite?\n")
b <- "D:/Descargas/Publicidad Oficial/data/raw/"
x24 <- as.data.table(suppressWarnings(read_excel(paste0(b,"Ejercido_P_lizasCOMSOC__Enero_a_diciembre_2024.xlsx"), sheet=2, skip=7, col_types="text")))
x24 <- x24[!is.na(Sector)]
setnames(x24, make.unique(names(x24)))
cat("  2024 (36101-36201): filas=", nrow(x24), "\n")
k <- x24[, .N, by=.(`Clave de la Entidad`, `Póliza`)]
cat("    pólizas distintas:", nrow(k), " renglones/póliza: media=", round(mean(k$N),2), " max=", max(k$N), "\n")
x25 <- as.data.table(suppressWarnings(read_excel(paste0(b,"COMSOC_ejercido_enero-diciembre_2025.xlsx"), sheet=4, skip=12, col_types="text")))
x25 <- x25[!is.na(Sector) & nchar(Sector)<60]
setnames(x25, make.unique(names(x25)))
cat("  2025 (36101-36201): filas=", nrow(x25), "\n")
k5 <- x25[, .N, by=.(Clave, `Póliza`)]
cat("    pólizas distintas:", nrow(k5), " renglones/póliza: media=", round(mean(k5$N),2), " max=", max(k5$N), "\n")
cat("    ¿'Núm.' es único?", uniqueN(x25[[1]]) == nrow(x25), " (", uniqueN(x25[[1]]), "de", nrow(x25), ")\n")
