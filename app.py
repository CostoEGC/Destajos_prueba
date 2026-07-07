import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os
import re
import requests
import json
import math
from zoneinfo import ZoneInfo
from PIL import Image
from bs4 import BeautifulSoup
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode, JsCode
from fpdf import FPDF
import io


# -----------------------------------

# =========================================================================
# CONFIGURACIÓN INICIAL DE LA PÁGINA
# =========================================================================
st.set_page_config(page_title="ERP Destajos EGC", layout="wide")

URL_API_SHEET = st.secrets["URL_API_SHEET"] if "URL_API_SHEET" in st.secrets else ""

# Nuevas columnas de Google Sheets
COLUMNAS_GS = ['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', 'C.C', 'Pagar', 'Fecha pago', 'Usuario']

def obtener_datos_gsheet():
    try:
        response = requests.get(URL_API_SHEET)
        data = response.json()
        df = pd.DataFrame(data[1:], columns=data[0])

        # Asegurar que existan todas las columnas requeridas
        for col in COLUMNAS_GS:
            if col not in df.columns:
                df[col] = ''

        # Limpieza de datos estricta
        df['Costo'] = pd.to_numeric(df['Costo'], errors='coerce').fillna(0.0)
        df['Pagar'] = df['Pagar'].apply(lambda x: True if str(x).strip().upper() == 'TRUE' else False)
        
        # LIMPIEZA EXTREMA DE FECHAS: Si no tiene un formato con '/' (ej. 12/05/2026), se borra por completo
        df['Fecha pago'] = df['Fecha pago'].astype(str).str.strip()
        df.loc[~df['Fecha pago'].str.contains(r'/', na=False), 'Fecha pago'] = ''
        
        df['Usuario'] = df['Usuario'].fillna('').astype(str).replace(['nan', 'NaN', 'None', 'null'], '')
        df['Destajista'] = df['Destajista'].fillna('').astype(str).replace(['nan', 'NaN', 'None', 'null'], '')
        df['C.C'] = df['C.C'].fillna('').astype(str).replace(['nan', 'NaN', 'None', 'null'], '')

        # Prefijo a Prototipo
        df['Prototipo'] = df['Prototipo'].apply(lambda x: f"Prototipo {x}" if "Prototipo" not in str(x) else x)

        return df[COLUMNAS_GS]
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        return pd.DataFrame(columns=COLUMNAS_GS)

def actualizar_datos_gsheet(df):
    try:
        df_export = df.copy()
        df_export['Pagar'] = df_export['Pagar'].astype(str)
        
        datos_a_enviar = [COLUMNAS_GS] + df_export[COLUMNAS_GS].values.tolist()
        response = requests.post(URL_API_SHEET, json=datos_a_enviar)
        if response.status_code != 200:
            st.error("⚠️ Hubo un problema al guardar en la nube.")
    except Exception as e:
        st.error(f"Error al enviar datos a Google Sheets: {e}")

# =========================================================================
# ⚙️ CONFIGURACIÓN DE DISEÑO Y VARIABLES GLOBALES
# =========================================================================
LISTA_DESTAJISTAS = [
    "Pablo Barragán (Albañilería)",
    "Andrés (Albañileriá)",
    "Miguel Leyva (Instalaciones)",
    "José López (Pisos)",
    "Guillermo (Pintura)",
    "Gerardo Zamora (yaso y pintura)"
]

LISTA_CC = [
    "CC 001 - Cimentación",
    "CC 002 - Estructura",
    "CC 003 - Acabados",
    "CC 004 - Instalaciones",
    "CC 005 - Urbanización"
]

def mostrar_cabecera_con_logo(titulo, subtitulo=None):
    col_texto, col_logo = st.columns([8, 2])
    with col_texto:
        st.title(titulo)
        if subtitulo:
            st.write(subtitulo)
    with col_logo:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)

# =========================================================================
# INICIALIZACIÓN DE ESTADOS
# =========================================================================
if 'usuario' not in st.session_state:
    st.session_state.usuario = None

if 'df' not in st.session_state:
    st.session_state.df = obtener_datos_gsheet()
    st.session_state.df_original = st.session_state.df.copy()

df = st.session_state.df

# --- 1. FORMULARIO DE ACCESO ---
def login():
    mostrar_cabecera_con_logo("🔐 Control de estimaciones", "Por favor, introduce tus credenciales para ingresar.")
    with st.container():
        usuario = st.text_input("Usuario", key="input_user")
        contrasena = st.text_input("Contraseña", type="password", key="input_pass")
        
        if st.button("Ingresar", use_container_width=False):
            usuarios_validos = st.secrets["usuarios"] if "usuarios" in st.secrets else {"admin":"123"}
            if usuario in usuarios_validos and usuarios_validos[usuario] == contrasena:
                st.session_state.usuario = usuario
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos")

if st.session_state.usuario is None:
    login()
    st.stop()

def clave_ordenamiento(val):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(val))]

def clave_ordenamiento_proto(val):
    val_str = str(val).replace("Prototipo ", "").strip()
    match = re.match(r"(\d+)(.*)", val_str)
    if match:
        num = int(match.group(1))
        letra = match.group(2)
        peso_letra = 0 if letra == "" else (1 if letra == "+" else 2)
        return (num, peso_letra, letra)
    return (float('inf'), val_str)

# --- MENÚ DE NAVEGACIÓN LATERAL ---
st.sidebar.title(f"👷 {st.session_state.usuario}")
menu = st.sidebar.radio("Menú Principal:", [
    "Registro de Destajos", 
    "Dashboard (Gráficos y Visor)", 
    "Mapa Interactivo"
])

if st.sidebar.button("💾 GUARDAR CAMBIOS"):
    df_grid = st.session_state.get('aggrid_data', None)
    if df_grid is not None:
        df_actualizado = pd.DataFrame(df_grid)
        
        filas_invalidas = df_actualizado[(df_actualizado['Pagar'] == True) & 
                                         ((df_actualizado['Destajista'] == '') | (df_actualizado['C.C'] == '') | 
                                          (df_actualizado['Destajista'].isnull()) | (df_actualizado['C.C'].isnull()))]
        
        if not filas_invalidas.empty:
            st.sidebar.error("❌ ERROR: Hay filas marcadas para 'Pagar' pero sin Destajista o C.C asignado. No se guardaron los cambios.")
        else:
            with st.spinner("Sincronizando con Google..."):
                ahora = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%d/%m/%Y %H:%M:%S")
                usuario_actual = st.session_state.usuario
                
                mask_nuevos_pagos = (df_actualizado['Pagar'] == True) & (df_actualizado['Fecha pago'].astype(str) == '')
                df_actualizado.loc[mask_nuevos_pagos, 'Fecha pago'] = ahora
                df_actualizado.loc[mask_nuevos_pagos, 'Usuario'] = usuario_actual
                
                st.session_state.df.update(df_actualizado)
                
                actualizar_datos_gsheet(st.session_state.df)
                st.session_state.df_original = st.session_state.df.copy()
                st.sidebar.success("¡Datos guardados!")
                st.rerun()

# REPORTE PDF
@st.dialog("📄 Generar Reporte PDF")
def dialogo_reporte():
    st.write("Selecciona el rango de fechas para el reporte:")
    rango = st.date_input("Rango de Fechas", value=[], key="pdf_dates")
    orientacion = st.radio("Orientación", ["Vertical", "Horizontal"])
    
    if st.button("Imprimir PDF"):
        if len(rango) == 2:
            fecha_inicio, fecha_fin = rango[0], rango[1]
            
            df_rep = st.session_state.df.copy()
            df_rep = df_rep[df_rep['Pagar'] == True]
            df_rep['Fecha_dt'] = pd.to_datetime(df_rep['Fecha pago'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date
            df_rep = df_rep[(df_rep['Fecha_dt'] >= fecha_inicio) & (df_rep['Fecha_dt'] <= fecha_fin)]
            
            if df_rep.empty:
                st.warning("No hay pagos registrados en este rango de fechas.")
            else:
                resumen = df_rep.groupby(['Destajista', 'C.C'])['Costo'].sum().reset_index()
                resumen.columns = ['Destajista', 'Centro de Costo', 'Cantidad Pagada']
                
                pdf = FPDF(orientation='P' if orientacion == 'Vertical' else 'L', unit='mm', format='Letter')
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(0, 10, f"Reporte de Pagos ({fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')})", ln=True, align='C')
                pdf.ln(10)
                
                pdf.set_font("Arial", 'B', 12)
                col_w = [80, 60, 50]
                pdf.cell(col_w[0], 10, 'Destajista', 1, 0, 'C')
                pdf.cell(col_w[1], 10, 'Centro de Costo', 1, 0, 'C')
                pdf.cell(col_w[2], 10, 'Cantidad Pagada', 1, 1, 'C')
                
                pdf.set_font("Arial", '', 10)
                total_global = 0
                for _, row in resumen.iterrows():
                    pdf.cell(col_w[0], 10, str(row['Destajista'])[:40], 1)
                    pdf.cell(col_w[1], 10, str(row['Centro de Costo'])[:30], 1)
                    pdf.cell(col_w[2], 10, f"${row['Cantidad Pagada']:,.2f}", 1, 1, 'R')
                    total_global += row['Cantidad Pagada']
                
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(col_w[0] + col_w[1], 10, 'TOTAL', 1, 0, 'R')
                pdf.cell(col_w[2], 10, f"${total_global:,.2f}", 1, 1, 'R')
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
                st.download_button(
                    label="⬇️ Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"Reporte_Pagos_{fecha_inicio}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
        else:
            st.warning("Selecciona una fecha de inicio y una de fin.")

if st.sidebar.button("📄 Reportes"):
    dialogo_reporte()

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state.usuario = None
    st.rerun()

# =========================================================================
# CAPA DE COMPATIBILIDAD PARA DASHBOARD Y MAPA
# =========================================================================
df_compat = df.copy()
df_compat['Precio'] = df_compat['Costo']
df_compat['Pago_1'] = df_compat.apply(lambda x: x['Costo'] if x['Pagar'] else 0.0, axis=1)
df_compat['Pago_2'] = 0.0
df_compat['Estado'] = df_compat['Pagar'].apply(lambda x: 'Pagado' if x else 'Pendiente')
df_compat['Fecha_Pago'] = df_compat['Fecha pago']
df_compat['Fecha_Pago_2'] = '-'

partidas_unicas_global = df_compat['Partida'].unique() if not df_compat.empty else []
paleta_colores_global = px.colors.qualitative.Alphabet + px.colors.qualitative.Light24 + px.colors.qualitative.Dark24
mapa_colores_partida = {partida: paleta_colores_global[i % len(paleta_colores_global)] for i, partida in enumerate(partidas_unicas_global)}

if 'lote_actual' not in st.session_state:
    st.session_state.lote_actual = str(df_compat['Lote'].unique()[0]) if not df_compat.empty else "1"

if 'mostrar_todos_mapa' not in st.session_state:
    st.session_state.mostrar_todos_mapa = False

# =========================================================================
# PESTAÑA 1: REGISTRO DE DESTAJOS
# =========================================================================
if menu == "Registro de Destajos":
    mostrar_cabecera_con_logo("📝 Control de Pagos Destajos")
    
    st.markdown("### ⏳ Filtros de Tabla")
    
    def limpiar_filtros():
        st.session_state.f_proto = "Todos"
        st.session_state.f_manzana = "Todos"
        st.session_state.f_estado = "Todos"
        st.session_state.f_lote = []
        st.session_state.f_fechas = []
        st.session_state.f_concepto = "Todos"
        st.session_state.f_destajista = "Todos"
    
    if st.button("🧹 Limpiar todos los filtros"):
        limpiar_filtros()
        st.rerun()

    if 'f_proto' not in st.session_state: limpiar_filtros()

    lista_protos = ["Todos"] + sorted([str(x) for x in df['Prototipo'].unique()], key=clave_ordenamiento_proto)
    lista_manzanas = ["Todos"] + sorted([str(x) for x in df['Manzana'].unique()], key=clave_ordenamiento)
    lista_lotes = sorted([str(x) for x in df['Lote'].unique()], key=clave_ordenamiento)
    lista_destajistas = ["Todos"] + sorted(LISTA_DESTAJISTAS)
    
    conceptos_unicos = df['Partida'].dropna().unique()
    conceptos_limpios = []
    for c in conceptos_unicos:
        match = re.match(r'^(\d+)[\.-]\s*(.*)', str(c))
        if match:
            num = int(match.group(1))
            nombre = match.group(2).strip()
            conceptos_limpios.append((num, nombre, c))
        else:
            conceptos_limpios.append((9999, str(c).strip(), c))
    
    conceptos_limpios.sort(key=lambda x: (x[0], x[1]))
    nombres_conceptos_mostrar = ["Todos"] + [x[1] for x in conceptos_limpios]
    dic_conceptos_reverso = {x[1]: x[2] for x in conceptos_limpios} 
    
    with st.expander("🛠️ Panel de Filtros", expanded=True):
        f_col1, f_col2 = st.columns(2)
        
        with f_col1:
            val_proto = f_col1.selectbox("Prototipo:", lista_protos, index=lista_protos.index(st.session_state.f_proto) if st.session_state.f_proto in lista_protos else 0)
            val_lote = f_col1.multiselect("Selecciona el Lote:", lista_lotes, default=st.session_state.f_lote)
            val_fechas = f_col1.date_input("Filtrar por Fecha (Rango):", value=st.session_state.f_fechas)
            val_destajista = f_col1.selectbox("Destajista:", lista_destajistas, index=lista_destajistas.index(st.session_state.f_destajista) if st.session_state.f_destajista in lista_destajistas else 0)

        with f_col2:
            val_manzana = f_col2.selectbox("Manzana:", lista_manzanas, index=lista_manzanas.index(st.session_state.f_manzana) if st.session_state.f_manzana in lista_manzanas else 0)
            val_estado = f_col2.selectbox("Estado de Pago:", ["Todos", "Pendiente", "Pagado"], index=["Todos", "Pendiente", "Pagado"].index(st.session_state.f_estado) if st.session_state.f_estado in ["Todos", "Pendiente", "Pagado"] else 0)
            val_concepto = f_col2.selectbox("Buscar Concepto:", nombres_conceptos_mostrar, index=nombres_conceptos_mostrar.index(st.session_state.f_concepto) if st.session_state.f_concepto in nombres_conceptos_mostrar else 0)
            
        st.session_state.f_proto = val_proto
        st.session_state.f_lote = val_lote
        st.session_state.f_fechas = val_fechas
        st.session_state.f_destajista = val_destajista
        st.session_state.f_manzana = val_manzana
        st.session_state.f_estado = val_estado
        st.session_state.f_concepto = val_concepto

    df_filtrado = df.copy()
    
    if st.session_state.f_proto != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Prototipo'] == st.session_state.f_proto]
    if st.session_state.f_manzana != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Manzana'] == st.session_state.f_manzana]
    if st.session_state.f_lote:
        df_filtrado = df_filtrado[df_filtrado['Lote'].isin(st.session_state.f_lote)]
    if st.session_state.f_destajista != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Destajista'] == st.session_state.f_destajista]
    if st.session_state.f_estado != "Todos":
        if st.session_state.f_estado == "Pagado":
            df_filtrado = df_filtrado[df_filtrado['Pagar'] == True]
        else:
            df_filtrado = df_filtrado[df_filtrado['Pagar'] == False]
    if st.session_state.f_concepto != "Todos":
        concepto_original = dic_conceptos_reverso[st.session_state.f_concepto]
        df_filtrado = df_filtrado[df_filtrado['Partida'] == concepto_original]
    if len(st.session_state.f_fechas) == 2:
        df_filtrado['Fecha_dt'] = pd.to_datetime(df_filtrado['Fecha pago'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date
        df_filtrado = df_filtrado[(df_filtrado['Fecha_dt'] >= st.session_state.f_fechas[0]) & (df_filtrado['Fecha_dt'] <= st.session_state.f_fechas[1])]
        df_filtrado = df_filtrado.drop(columns=['Fecha_dt'])

    sum_precio = df_filtrado['Costo'].sum()
    
    df_interactivo = st.session_state.get('aggrid_data', df_filtrado.to_dict('records'))
    df_interactivo_pd = pd.DataFrame(df_interactivo)
    
    if not df_interactivo_pd.empty and 'Pagar' in df_interactivo_pd.columns:
        pagos_realizados = df_interactivo_pd[df_interactivo_pd['Pagar'] == True]['Costo'].sum()
    else:
        pagos_realizados = df_filtrado[df_filtrado['Pagar'] == True]['Costo'].sum()
        
    sum_pendiente = sum_precio - pagos_realizados

    lote_head = ", ".join(st.session_state.f_lote) if st.session_state.f_lote else "Todos"
    proto_head = st.session_state.f_proto
    
    st.markdown(f"""
    <div style="background-color:#1E3A8A; padding:15px; border-radius:10px; margin-bottom:15px; color:#FFFFFF;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size:20px; font-weight:bold;">🏠 Lote(s): {lote_head} | {proto_head}</div>
            <div style="font-size:18px; font-weight:bold; color: #39FF14;">
                🔹 Pagos sumados (Checks activos): ${pagos_realizados:,.2f}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"<div style='text-align: right; font-size: 14px; font-weight: bold; color: #3B82F6;'>🔹➔ Costo: ${sum_precio:,.2f} | Por pagar: ${sum_pendiente:,.2f}</div>", unsafe_allow_html=True)

    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
    
    dest_masivo = col_b1.selectbox("Destajista masivo:", ["Seleccionar..."] + LISTA_DESTAJISTAS, label_visibility="collapsed")
    if col_b1.button("Asignar destajista masivo"):
        if dest_masivo != "Seleccionar...":
            df_filtrado['Destajista'] = dest_masivo
            st.rerun()

    cc_masivo = col_b2.selectbox("C.C masivo:", ["Seleccionar..."] + LISTA_CC, label_visibility="collapsed")
    if col_b2.button("Asignar C.C masivo"):
        if cc_masivo != "Seleccionar...":
            df_filtrado['C.C'] = cc_masivo
            st.rerun()
            
    st.markdown("<br>", unsafe_allow_html=True)
    col_c1, col_c2 = st.columns(2)
    
    if col_c1.button("☑️ Seleccionar Todos (Filtrados)"):
        idxs = df_filtrado.index
        st.session_state.df.loc[idxs, 'Pagar'] = True
        st.rerun()

    if col_c2.button("🔲 Seleccionar Ninguno (Filtrados)"):
        idxs = df_filtrado.index
        mask_desbloqueados = st.session_state.df.loc[idxs, 'Fecha pago'].astype(str) == ''
        st.session_state.df.loc[idxs[mask_desbloqueados], 'Pagar'] = False
        st.rerun()

    # --- CONFIGURACIÓN DE AGGRID ---
    gb = GridOptionsBuilder.from_dataframe(df_filtrado)
    
    gb.configure_default_column(editable=False, sortable=False, filter=False, wrapText=True, autoHeight=True)
    
    if '_index' in df_filtrado.columns:
        gb.configure_column('_index', hide=True)

    # JsCode MÁS ESTRICTO: Solo bloquea si encuentra una cadena que contenga '/' (es decir, una fecha genuina)
    bloqueo_js = JsCode("""
    function(params) {
        var fp = params.data['Fecha pago'];
        if (fp != null && fp !== undefined) {
            var fpStr = String(fp).trim();
            if (fpStr.length >= 8 && fpStr.indexOf('/') !== -1) {
                return false; // Bloqueado, tiene fecha real
            }
        }
        return true; // Editable, no es una fecha válida
    }
    """)
    
    #celdas editables en la tabla
    estilo_js = JsCode("""
    function(params) {
        var baseStyle = {'color': '#ffffff', 'backgroundColor': '#000000', 'borderBottom': '1px solid #333333'};  // Celdas normales
        var fp = params.data['Fecha pago'];
        if (fp != null && fp !== undefined) {
            var fpStr = String(fp).trim();
            if (fpStr.length >= 8 && fpStr.indexOf('/') !== -1) {
                baseStyle['backgroundColor'] = '#2d2d2d';  // Celdas bloqueadas al guardar
                baseStyle['color'] = '#888888';
            }
        }
        return baseStyle;
    }
    """)

    gb.configure_column('Lote', cellStyle=estilo_js)
    gb.configure_column('Manzana', cellStyle=estilo_js)
    gb.configure_column('Prototipo', cellStyle=estilo_js)
    gb.configure_column('Partida', width=300, cellStyle=estilo_js)
    
    moneda_js = JsCode("""
    function(params) {
        if (params.value == null) return '$0.00';
        return '$' + parseFloat(params.value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    """)
    gb.configure_column('Costo', valueFormatter=moneda_js, cellStyle=estilo_js)
    
    gb.configure_column('Destajista', editable=bloqueo_js, cellEditor='agSelectCellEditor', cellEditorParams={'values': LISTA_DESTAJISTAS}, cellStyle=estilo_js)
    gb.configure_column('C.C', editable=bloqueo_js, cellEditor='agSelectCellEditor', cellEditorParams={'values': LISTA_CC}, cellStyle=estilo_js)
    
    checkbox_js = JsCode("""
    function(params) {
        if(params.data['Costo'] == 0 || params.data['Costo'] == '0.0' || params.data['Costo'] == 0.0) {
            return 'N/A';
        }
        return params.value;
    }
    """)
    gb.configure_column('Pagar', editable=bloqueo_js, cellDataType='boolean', valueFormatter=checkbox_js, cellStyle=estilo_js)
    
    gb.configure_column('Fecha pago', cellStyle=estilo_js)
    gb.configure_column('Usuario', cellStyle=estilo_js)

    gridOptions = gb.build()

    #cambio de color tabla registro destajos fondo general y encabezados
    st.markdown("""
    <style>
    .ag-theme-alpine-dark {
        --ag-background-color: #000000;         #fondo de la tabla
        --ag-header-background-color: #111111;  #Fondo de encabezados
        --ag-header-foreground-color: #ffffff;  #Texto encabezados
        --ag-row-border-color: #333333;         #lienas horizontales
        --ag-font-size: 17px;
    }
    </style>
    """, unsafe_allow_html=True)

    grid_response = AgGrid(
        df_filtrado,
        gridOptions=gridOptions,
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        allow_unsafe_jscode=True,
        theme='alpine-dark',
        height=600,
        fit_columns_on_grid_load=False
    )

    st.session_state['aggrid_data'] = grid_response['data']

# =========================================================================
# PESTAÑA 2: DASHBOARD INTERACTIVO Y GERENCIAL
# =========================================================================
elif menu == "Dashboard (Gráficos y Visor)":
    mostrar_cabecera_con_logo("📊 Visor Estadístico e Indicadores")
    
    def ordenar_prototipos(val):
        match = re.search(r"(\d+)(.*)", str(val))
        if match:
            return (int(match.group(1)), match.group(2))
        return (float('inf'), str(val))

    st.markdown("### 🔍 Panel de Control y Filtros Dinámicos")
    
    d_col1, d_col2, d_col3 = st.columns(3)
    protos_disponibles = sorted(df_compat['Prototipo'].unique(), key=ordenar_prototipos)
    lotes_disponibles = list(df_compat['Lote'].unique())
    destajistas_disponibles = ["Todos"] + list(df_compat['Destajista'].dropna().unique())
    
    if 'tab2_lotes_seleccionados' not in st.session_state:
        st.session_state.tab2_lotes_seleccionados = lotes_disponibles
        
    protos_dash = d_col1.multiselect("Filtrar por Prototipos:", options=protos_disponibles, default=protos_disponibles)
    lotes_dash = d_col2.multiselect("Filtrar por Lotes:", options=lotes_disponibles, key="tab2_lotes_seleccionados")
    destajista_dash = d_col3.selectbox("Filtrar por Destajista Global:", options=destajistas_disponibles)
    
    df_dash = df_compat[(df_compat['Lote'].isin(lotes_dash)) & (df_compat['Prototipo'].isin(protos_dash))].copy()
    if destajista_dash != "Todos":
        df_dash = df_dash[df_dash['Destajista'] == destajista_dash]
    
    if df_dash.empty:
        st.warning("⚠️ No hay datos para mostrar con los filtros seleccionados.")
    else:
        df_dash['Total_Pagado_Real'] = pd.to_numeric(df_dash['Pago_1']) + pd.to_numeric(df_dash['Pago_2'])
        
        monto_total = df_dash['Precio'].sum()
        monto_pagado = df_dash['Total_Pagado_Real'].sum()
        monto_pendiente = monto_total - monto_pagado
        
        df_pagados = df_dash[df_dash['Estado'] == 'Pagado'] 
        df_pendientes = df_dash[df_dash['Estado'] != 'Pagado']
        
        st.markdown("<br>", unsafe_allow_html=True)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
        titulo_kpi = "💰 Presupuesto Global Seleccionado" if destajista_dash == "Todos" else f"💰 Asignado a {destajista_dash}"
        kpi1.metric(titulo_kpi, f"${monto_total:,.2f}")
        
        if monto_total > 0:
            pct_pagado = (monto_pagado / monto_total) * 100
            pct_pendiente = (monto_pendiente / monto_total) * 100
        else:
            pct_pagado, pct_pendiente = 0, 0
            
        kpi2.metric("✅ Monto Total Pagado", f"${monto_pagado:,.2f}", f"{pct_pagado:.2f}% de Avance Real")
        kpi3.metric("🚨 Deuda Pendiente por Pagar", f"${monto_pendiente:,.2f}", f"-{pct_pendiente:.2f}%", delta_color="inverse")
        
        total_partidas_dash = len(df_dash)
        partidas_pagadas_dash = len(df_pagados)
        kpi4.metric("📋 Partidas Completadas (100%)", f"{partidas_pagadas_dash} / {total_partidas_dash}", f"{(partidas_pagadas_dash/total_partidas_dash*100) if total_partidas_dash>0 else 0:.1f}%")
        
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>📋 Resumen Individual por Lote y Prototipo</h3>", unsafe_allow_html=True)
        
        df_dash_clean = df_dash.copy()
        df_dash_clean['Deuda_Pendiente'] = df_dash_clean['Precio'] - df_dash_clean['Total_Pagado_Real']
        
        df_resumen = df_dash_clean.groupby(['Lote', 'Prototipo'])[['Precio', 'Total_Pagado_Real', 'Deuda_Pendiente']].sum().reset_index()
        df_resumen.columns = ['Lote', 'Prototipo', 'Valor Total', 'Total Pagado', 'Deuda Pendiente']
        
        styled_resumen = df_resumen.style.format({
            'Valor Total': '${:,.2f}',
            'Total Pagado': '${:,.2f}',
            'Deuda Pendiente': '${:,.2f}'
        }).set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])])
        
        col_espacio_izq, col_tabla_centro, col_espacio_der = st.columns([1, 6, 1])
        with col_tabla_centro:
            st.dataframe(styled_resumen, use_container_width=True, hide_index=True)

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("### 📈 Inteligencia de Negocios y Gráficos")
        
        tab_graf1, tab_graf2 = st.tabs(["💰 Control por Prototipos y Lotes", "👷 Control de Destajistas (Contratistas)"])
        
        with tab_graf1:
            g_col1, g_col2 = st.columns(2)
            
            df_proto_graf = df_dash.groupby(['Prototipo', 'Estado'])['Precio'].sum().reset_index()
            fig_proto = px.bar(df_proto_graf, x='Prototipo', y='Precio', color='Estado', 
                               title="Comportamiento Financiero por Prototipo",
                               barmode='group', text_auto='.2s',
                               color_discrete_map={'Pagado': '#10B981', 'Pago Parcial': '#F59E0B', 'Pendiente': '#EF4444'})
            fig_proto.update_traces(textposition='outside')
            g_col1.plotly_chart(fig_proto, use_container_width=True)
            
            fig_tree = px.treemap(df_dash, path=[px.Constant("Proyecto EGC"), 'Prototipo', 'Lote', 'Estado'], values='Precio',
                                  title="Distribución del Presupuesto (Clic para explorar)",
                                  color='Estado', color_discrete_map={'Pagado': '#10B981', 'Pago Parcial': '#F59E0B', 'Pendiente': '#EF4444', '(?)': '#cbd5e1'})
            fig_tree.update_traces(root_color="lightgrey")
            fig_tree.update_layout(margin=dict(t=50, l=25, r=25, b=25))
            g_col2.plotly_chart(fig_tree, use_container_width=True)
            
            df_lotes_graf = df_dash.groupby(['Lote', 'Estado'])['Precio'].sum().reset_index()
            fig_lote = px.bar(df_lotes_graf, x='Lote', y='Precio', color='Estado', 
                              title="Avance Financiero Específico por Lote",
                              color_discrete_map={'Pagado': '#10B981', 'Pago Parcial': '#F59E0B', 'Pendiente': '#EF4444'})
            st.plotly_chart(fig_lote, use_container_width=True)
            
        with tab_graf2:
            g_col3, g_col4 = st.columns(2)
            
            df_pagos_efectivos = df_dash[df_dash['Total_Pagado_Real'] > 0]
            if not df_pagos_efectivos.empty:
                df_dest = df_pagos_efectivos.groupby('Destajista')['Total_Pagado_Real'].sum().reset_index()
                fig_dest = px.pie(df_dest, names='Destajista', values='Total_Pagado_Real', 
                                  title="🏆 Distribución de Dinero Pagado",
                                  hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                fig_dest.update_traces(textposition='inside', textinfo='percent+label')
                g_col3.plotly_chart(fig_dest, use_container_width=True)
            else:
                g_col3.info("Aún no hay pagos ejecutados en la selección actual para mostrar.")
                
            df_deudores = df_dash[df_dash['Total_Pagado_Real'] < df_dash['Precio']].copy()
            if not df_deudores.empty:
                df_deudores['Deuda'] = df_deudores['Precio'] - df_deudores['Total_Pagado_Real']
                df_deudores_clean = df_deudores.fillna("Sin Asignar")
                df_deuda = df_deudores_clean.groupby('Destajista')['Deuda'].sum().reset_index().sort_values('Deuda', ascending=True)
                fig_deuda = px.bar(df_deuda, y='Destajista', x='Deuda', orientation='h',
                                   title="🚨 Pagos Pendientes por Destajista (Deuda Restante)",
                                   color_discrete_sequence=['#EF4444'], text_auto='$.2s')
                g_col4.plotly_chart(fig_deuda, use_container_width=True)
            else:
                g_col4.success("¡Excelente! No hay deuda pendiente para la selección actual.")

# =========================================================================
# PESTAÑA 3: MAPA INTERACTIVO 
# =========================================================================
elif menu == "Mapa Interactivo":
    mostrar_cabecera_con_logo("🗺️ Plano Interactivo Dinámico", "Visualización gráfica del avance del desarrollo.")

    def hex_to_rgba(hex_val, opacity):
        hex_val = hex_val.lstrip('#')
        if len(hex_val) == 6:
            return f"rgba({int(hex_val[0:2], 16)}, {int(hex_val[2:4], 16)}, {int(hex_val[4:6], 16)}, {opacity})"
        return "rgba(0,0,0,0)"

    COORDENADAS_LOTES = {
        "1": {"x": 794, "y": 379}, "2": {"x": 799, "y": 346}, "3": {"x": 804, "y": 310}, "4": {"x": 807, "y": 285},
        "5": {"x": 811, "y": 254}, "6": {"x": 818, "y": 225}, "7": {"x": 828, "y": 195}, "8": {"x": 825, "y": 169},
        "9": {"x": 827, "y": 138}, "10": {"x": 713, "y": 151}, "11": {"x": 676, "y": 143}, "12": {"x": 646, "y": 139},
        "13": {"x": 617, "y": 141}, "14": {"x": 589, "y": 132}, "15": {"x": 560, "y": 126}, "16": {"x": 532, "y": 127},
        "17": {"x": 503, "y": 118}, "18": {"x": 469, "y": 123}, "19": {"x": 443, "y": 115}, "20": {"x": 416, "y": 109},
        "21": {"x": 386, "y": 108}, "22": {"x": 358, "y": 103}, "23": {"x": 327, "y": 99}, "24": {"x": 300, "y": 96},
        "25": {"x": 270, "y": 95}, "26": {"x": 240, "y": 89}, "27": {"x": 212, "y": 87}, "28": {"x": 182, "y": 82},
        "29": {"x": 152, "y": 73}, "30": {"x": 122, "y": 70}, "31": {"x": 282, "y": 239}, "32": {"x": 320, "y": 245},
        "33": {"x": 358, "y": 250}, "34": {"x": 393, "y": 256}, "35": {"x": 425, "y": 260}, "36": {"x": 459, "y": 264},
        "37": {"x": 498, "y": 272}, "38": {"x": 532, "y": 278}, "39": {"x": 568, "y": 279}, "40": {"x": 603, "y": 285},
        "41": {"x": 634, "y": 293}, "42": {"x": 675, "y": 295}, "43": {"x": 656, "y": 379}, "44": {"x": 612, "y": 379},
        "45": {"x": 579, "y": 373}, "46": {"x": 546, "y": 367}, "47": {"x": 510, "y": 364}, "48": {"x": 475, "y": 358},
        "49": {"x": 437, "y": 355}, "50": {"x": 407, "y": 351}, "51": {"x": 381, "y": 348}, "52": {"x": 349, "y": 343},
        "53": {"x": 311, "y": 337}, "54": {"x": 268, "y": 336}, "55": {"x": 151, "y": 185}, "56": {"x": 146, "y": 217},
        "57": {"x": 144, "y": 245}, "58": {"x": 142, "y": 275}, "59": {"x": 133, "y": 302}, "60": {"x": 135, "y": 336},
        "61": {"x": 129, "y": 364}, "62": {"x": 126, "y": 395}, "63": {"x": 126, "y": 421}, "64": {"x": 121, "y": 449},
        "65": {"x": 115, "y": 479}, "66": {"x": 112, "y": 511}, "67": {"x": 108, "y": 536}, "68": {"x": 108, "y": 568},
        "69": {"x": 105, "y": 598}, "70": {"x": 99, "y": 623}, "71": {"x": 94, "y": 654}, "72": {"x": 96, "y": 683},
        "73": {"x": 92, "y": 713}, "74": {"x": 88, "y": 743}, "75": {"x": 87, "y": 772}, "76": {"x": 81, "y": 803},
        "77": {"x": 254, "y": 587}, "78": {"x": 262, "y": 560}, "79": {"x": 264, "y": 527}, "80": {"x": 268, "y": 500},
        "81": {"x": 273, "y": 470}, "82": {"x": 277, "y": 443}, "83": {"x": 365, "y": 458}, "84": {"x": 362, "y": 489},
        "85": {"x": 358, "y": 526}, "86": {"x": 359, "y": 560}, "87": {"x": 349, "y": 593}, "88": {"x": 224, "y": 688},
        "89": {"x": 267, "y": 697}, "90": {"x": 301, "y": 699}, "91": {"x": 330, "y": 708}, "92": {"x": 360, "y": 711},
        "93": {"x": 393, "y": 718}, "94": {"x": 427, "y": 717}, "95": {"x": 462, "y": 728}, "96": {"x": 496, "y": 734},
        "97": {"x": 531, "y": 738}, "98": {"x": 566, "y": 739}, "99": {"x": 604, "y": 744}, "100": {"x": 636, "y": 751},
        "101": {"x": 679, "y": 757}, "102": {"x": 704, "y": 848}, "103": {"x": 663, "y": 843}, "104": {"x": 625, "y": 835},
        "105": {"x": 590, "y": 831}, "106": {"x": 555, "y": 826}, "107": {"x": 520, "y": 825}, "108": {"x": 484, "y": 819},
        "109": {"x": 453, "y": 813}, "110": {"x": 416, "y": 809}, "111": {"x": 383, "y": 804}, "112": {"x": 346, "y": 798}, "113": {"x": 310, "y": 794}, "114": {"x": 274, "y": 789}, "115": {"x": 241, "y": 789}, "116": {"x": 207, "y": 782},
        "117": {"x": 29, "y": 902}, "118": {"x": 58, "y": 910}, "119": {"x": 85, "y": 913}, "120": {"x": 115, "y": 920},
        "121": {"x": 145, "y": 924}, "122": {"x": 174, "y": 927}, "123": {"x": 203, "y": 929}, "124": {"x": 233, "y": 933},
        "125": {"x": 260, "y": 937}, "126": {"x": 288, "y": 944}, "127": {"x": 319, "y": 940}, "128": {"x": 348, "y": 952},
        "129": {"x": 379, "y": 951}, "130": {"x": 406, "y": 958}, "131": {"x": 435, "y": 962}, "132": {"x": 463, "y": 962},
        "133": {"x": 495, "y": 966}, "134": {"x": 524, "y": 971}, "135": {"x": 551, "y": 975}, "136": {"x": 581, "y": 980},
        "137": {"x": 610, "y": 985}, "138": {"x": 638, "y": 988}, "139": {"x": 667, "y": 993}, "140": {"x": 696, "y": 996},
        "141": {"x": 725, "y": 999}, "142": {"x": 768, "y": 1006}, "143": {"x": 901, "y": 1015}, "144": {"x": 893, "y": 985},
        "145": {"x": 885, "y": 959}, "146": {"x": 874, "y": 930}, "147": {"x": 864, "y": 904}, "148": {"x": 859, "y": 875},
        "149": {"x": 848, "y": 846}, "150": {"x": 837, "y": 813}, "151": {"x": 822, "y": 765},
    }

    lotes_datos_mapa = []
    for lote_num, coords in COORDENADAS_LOTES.items():
        df_lote_mapa = df_compat[df_compat['Lote'].astype(str).str.strip() == str(lote_num)].copy()
        
        if not df_lote_mapa.empty:
            total_partidas = len(df_lote_mapa)
            df_lote_mapa['Total_Pagado_Real'] = pd.to_numeric(df_lote_mapa['Pago_1']) + pd.to_numeric(df_lote_mapa['Pago_2'])
            total_precio_lote = df_lote_mapa['Precio'].sum()
            total_pagado_lote = df_lote_mapa['Total_Pagado_Real'].sum()
            
            porcentaje = (total_pagado_lote / total_precio_lote * 100) if total_precio_lote > 0 else 0
            pagadas_completas = len(df_lote_mapa[df_lote_mapa['Estado'] == 'Pagado'])
            
            if porcentaje == 0:
                color_lote = "🔴 No iniciado"
                hex_color = "#EF4444"      # Rojo
            elif 0 < porcentaje <= 50:
                color_lote = "⚫ Obra negra"
                hex_color = "#57534E"      # Gris oscuro
            elif 50 < porcentaje <= 60:
                color_lote = "⚪ Obra gris"
                hex_color = "#752BA7"      # Morado
            elif 60 < porcentaje <= 70:
                color_lote = "🟡 Obra blanca"
                hex_color = "#FADE50"      # Amarillo
            elif 70 < porcentaje <= 80:
                color_lote = "🟠 Pisos"
                hex_color = "#F97316"      # Naranja
            elif 80 < porcentaje <= 95:
                color_lote = "🔵 Equipamientos (avalúos)"
                hex_color = "#3B82F6"      # Azul
            else: 
                color_lote = "🟢 Detallado y entrega"
                hex_color = "#10B981"      # Verde
                
            lotes_datos_mapa.append({
                "Lote": f"Lote {lote_num}",
                "Lote_Id": str(lote_num),
                "x": coords["x"],
                "y": coords["y"],
                "Avance": f"{porcentaje:.1f}%",
                "Estado": color_lote,
                "Hex": hex_color,
                "Detalle": f"{pagadas_completas}/{total_partidas} Partidas al 100%"
            })

    if st.session_state.mostrar_todos_mapa:
        df_kpi = df_compat.copy()
        titulo_kpi = "🏠 Proyecto General (Todos los Lotes)"
    else:
        lote_puro_kpi = str(st.session_state.lote_actual)
        df_kpi = df_compat[df_compat['Lote'].astype(str).str.strip() == lote_puro_kpi].copy()
        
        prototipo_kpi = df_kpi['Prototipo'].iloc[0] if not df_kpi.empty else "N/A"
        titulo_kpi = f"🏠 Lote {lote_puro_kpi} - Prototipo {prototipo_kpi}"
        
    df_kpi['Total_Pagado_Real'] = pd.to_numeric(df_kpi['Pago_1']) + pd.to_numeric(df_kpi['Pago_2'])
    costo_total_mapa = df_kpi['Precio'].sum()
    pagado_mapa = df_kpi['Total_Pagado_Real'].sum()
    pendiente_mapa = costo_total_mapa - pagado_mapa

    st.markdown(f"""
    <div style="margin-bottom:20px;">
        <div style="margin-bottom: 15px; border-bottom: 1px solid rgba(128,128,128,0.3); padding-bottom: 10px;">
            <div style="font-size:24px; font-weight:bold;">{titulo_kpi}</div>
        </div>
        <div style="display: flex; justify-content: space-between; gap: 15px; flex-wrap: wrap;">
            <div style="flex: 1; text-align: center; background-color:rgba(128,128,128,0.1); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Costo Total</div>
                <div style="font-size:24px; font-weight:bold;">${costo_total_mapa:,.2f}</div>
            </div>
            <div style="flex: 1; text-align: center; background-color:rgba(16, 185, 129, 0.4); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Total Pagado Real</div>
                <div style="font-size:24px; font-weight:bold;">${pagado_mapa:,.2f}</div>
            </div>
            <div style="flex: 1; text-align: center; background-color:rgba(239, 68, 68, 0.5); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Total por Pagar</div>
                <div style="font-size:24px; font-weight:bold;">${pendiente_mapa:,.2f}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🔍 Filtros de Esferas (Partidas y Destajistas)")
        
    f_col_mapa1, f_col_mapa2 = st.columns(2)
    
    partidas_ordenadas = []
    for p in df_compat['Partida'].dropna().unique():
        if str(p).strip() and str(p) not in partidas_ordenadas:
            partidas_ordenadas.append(str(p))
            
    partidas_display = [f"{i}.- {p}" for i, p in enumerate(partidas_ordenadas, start=1)]
    destajistas_unicos_filtro = sorted([str(d) for d in df_compat['Destajista'].dropna().unique() if str(d).strip()], key=clave_ordenamiento)
    
    filtro_partidas_mapa_display = f_col_mapa1.multiselect(
        "Filtrar por Partida (Máx 4):", 
        options=partidas_display,
        max_selections=4
    )
    
    filtro_partidas_mapa = [val.split(".- ", 1)[1] for val in filtro_partidas_mapa_display]
    
    filtro_destajistas_mapa = f_col_mapa2.multiselect(
        "Filtrar por Destajista (Máx 4):", 
        options=destajistas_unicos_filtro,
        max_selections=4
    )
    
    filtros_activos = bool(filtro_partidas_mapa) or bool(filtro_destajistas_mapa)
    
    df_filtered = df_compat[df_compat['Estado'].isin(['Pagado', 'Pago Parcial'])].copy()
    if filtro_partidas_mapa:
        df_filtered = df_filtered[df_filtered['Partida'].isin(filtro_partidas_mapa)]
    if filtro_destajistas_mapa:
        df_filtered = df_filtered[df_filtered['Destajista'].isin(filtro_destajistas_mapa)]


    st.markdown("""
    <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; margin-bottom: 20px; padding: 12px; background-color: rgba(255,255,255,0.05); border-radius: 8px; justify-content: center; border: 1px solid rgba(255,255,255,0.1);">
        <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 14px; height: 14px; background-color: #EF4444; border-radius: 50%;"></div><span style="font-size: 12px;">0% No iniciado</span></div>
        <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 14px; height: 14px; background-color: #57534E; border-radius: 50%;"></div><span style="font-size: 12px;">1-50% Obra negra</span></div>
        <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 14px; height: 14px; background-color: #752Ba7; border-radius: 50%;"></div><span style="font-size: 12px;">51-60% Obra gris</span></div>
        <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 14px; height: 14px; background-color: #FDE047; border-radius: 50%;"></div><span style="font-size: 12px;">61-70% Obra blanca</span></div>
        <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 14px; height: 14px; background-color: #F97316; border-radius: 50%;"></div><span style="font-size: 12px;">71-80% Pisos</span></div>
        <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 14px; height: 14px; background-color: #3B82F6; border-radius: 50%;"></div><span style="font-size: 12px;">81-95% Equipamientos</span></div>
        <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 14px; height: 14px; background-color: #10B981; border-radius: 50%;"></div><span style="font-size: 12px;">96-100% Detallado y entrega</span></div>
    </div>
    """, unsafe_allow_html=True)


    col_mapa, col_info_lote = st.columns([5, 3])

    with col_info_lote:
        c_titulo, c_selector = st.columns([5, 5])
        with c_titulo:
            st.markdown("### 📋 Desglose:")
        with c_selector:
            if filtros_activos:
                lotes_validos_filtro = sorted([str(x) for x in df_filtered['Lote'].unique()], key=lambda x: int(x) if str(x).isdigit() else x)
                opciones_selector = ["Mostrar Todos"] + [f"Lote {k}" for k in lotes_validos_filtro]
            else:
                opciones_selector = ["Mostrar Todos"] + [f"Lote {k}" for k in COORDENADAS_LOTES.keys()]
                
            if st.session_state.mostrar_todos_mapa:
                valor_defecto_mapa = "Mostrar Todos"
            else:
                valor_defecto_mapa = f"Lote {st.session_state.lote_actual}"
                if valor_defecto_mapa not in opciones_selector:
                    st.session_state.mostrar_todos_mapa = True
                    st.rerun()
                    
            idx_t3 = opciones_selector.index(valor_defecto_mapa) if valor_defecto_mapa in opciones_selector else 0

            mapa_sel = st.selectbox(
                "Selector", 
                opciones_selector, 
                index=idx_t3, 
                label_visibility="collapsed"
            )
                
            if mapa_sel != valor_defecto_mapa:
                if mapa_sel == "Mostrar Todos":
                    st.session_state.mostrar_todos_mapa = True
                else:
                    st.session_state.mostrar_todos_mapa = False
                    st.session_state.lote_actual = str(mapa_sel.replace("Lote ", ""))
                st.rerun()
        
        st.markdown("<hr style='margin-top:0px;'>", unsafe_allow_html=True)

        if st.session_state.mostrar_todos_mapa:
            if filtros_activos:
                st.markdown("**Desglose de Filtros Activos (Todos los Lotes):**")
                if not df_filtered.empty:
                    html_table = (
                        "<div style='height: 700px; overflow-y: auto; font-family: sans-serif; font-size: 14px; width: 100%'>" 
                        "<table style='width: 100%; border-collapse: collapse; text-align: center; color: #d1d1d1;'>" 
                        "<thead style='position: sticky; top: 0; background-color: #262626; z-index: 10;'>" 
                        "<tr>"
                        "<th style='padding: 10px; border-bottom: 2px solid #ddd;'></th>" 
                        "<th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left;'>Lote</th>"
                        "<th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left;'>Partida</th>"
                        "<th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left;'>Destajista</th>"
                        "</tr></thead><tbody>"
                    )
                    
                    for _, row_lote in df_filtered.iterrows():
                        c_hex = mapa_colores_partida.get(row_lote['Partida'], '#3B82F6')
                        estado_row = row_lote['Estado']
                        destajista_str = row_lote['Destajista'] if pd.notna(row_lote['Destajista']) and row_lote['Destajista'] != "" else "Sin Asignar"
                        op_style = "1.0" if estado_row == 'Pagado' else "0.5"
                        
                        html_table += (
                            "<tr style='border-bottom: 1px solid #eee;'>"
                            f"<td style='padding: 8px;'><div style='width:16px; height:16px; border-radius:50%; background-color:{c_hex}; opacity:{op_style}; margin:auto;'></div></td>"
                            f"<td style='padding: 8px; text-align: left;'>{row_lote['Lote']}</td>"
                            f"<td style='padding: 8px; text-align: left;'>{row_lote['Partida']}</td>"
                            f"<td style='padding: 8px; text-align: left;'>{destajista_str}</td>"
                            "</tr>"
                        )
                    html_table += "</tbody></table></div>"
                    st.markdown(html_table, unsafe_allow_html=True)
                else:
                    st.info("No se encontraron partidas con avance que coincidan con los filtros seleccionados.")
            else:
                st.markdown("**Resumen General por Lote (Financiero):**")
                df_resumen_global = df_compat.copy()
                df_resumen_global['Total_Pagado_Real'] = pd.to_numeric(df_resumen_global['Pago_1']) + pd.to_numeric(df_resumen_global['Pago_2'])
                
                df_resumen_global_grp = df_resumen_global.groupby('Lote').agg(
                    Total_Partidas=('Partida', 'count'),
                    Pagadas=('Estado', lambda x: (x == 'Pagado').sum()),
                    Costo_Total=('Precio', 'sum'),
                    Pagado_Acum=('Total_Pagado_Real', 'sum')
                ).reset_index()
                
                df_resumen_global_grp['% Avance'] = (df_resumen_global_grp['Pagado_Acum'] / df_resumen_global_grp['Costo_Total']) * 100
                df_resumen_global_grp['% Avance'] = df_resumen_global_grp['% Avance'].apply(lambda x: f"{x:.1f}%")
                
                styled_global = df_resumen_global_grp[['Lote', 'Total_Partidas', 'Pagadas', 'Costo_Total', '% Avance']].style.format({'Costo_Total': '${:,.2f}'}).set_properties(**{'text-align': 'center'})
                st.dataframe(styled_global, use_container_width=True, hide_index=True, height=480)
        else:
            lote_puro_num = str(st.session_state.lote_actual)
            
            if filtros_activos:
                st.markdown(f"**Desglose Filtrado (Lote {lote_puro_num}):**")
                df_desglose_lote = df_filtered[df_filtered['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Precio']].copy()
            else:
                st.markdown(f"**Desglose General (Lote {lote_puro_num}):**")
                df_desglose_lote = df_compat[df_compat['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Precio']].copy()
            
            if not df_desglose_lote.empty:
                def formatear_estado_icono(val):
                    if val == "Pagado": return "🟢 100% PAGADO"
                    elif val == "Pago Parcial": return "🟡 PAGO PARCIAL"
                    return "🔴 PENDIENTE"
                    
                df_desglose_lote['Estatus'] = df_desglose_lote['Estado'].apply(formatear_estado_icono)
                
                html_table = (
                    "<div style='height: 700px; overflow-y: auto; font-family: sans-serif; font-size: 14px; width: 100%'>" 
                    "<table style='width: 100%; border-collapse: collapse; text-align: center; color: #d1d1d1;'>" 
                    "<thead style='position: sticky; top: 0; background-color: #262626; z-index: 10;'>" 
                    "<tr>"
                    "<th style='padding: 10px; border-bottom: 2px solid #ddd;'></th>" 
                    "<th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left; '>Partida</th>"
                    "<th style='padding: 10px; border-bottom: 2px solid #ddd;'>Estatus</th>"
                    "<th style='padding: 10px; border-bottom: 2px solid #ddd;'>Precio</th>"
                    "</tr></thead><tbody>"
                )
                
                for _, row_lote in df_desglose_lote.iterrows():
                    c_hex = mapa_colores_partida.get(row_lote['Partida'], '#3B82F6')
                    op_style = "1.0" if row_lote['Estado'] == 'Pagado' else "0.5" if filtros_activos else "1.0"

                    html_table += (
                        "<tr style='border-bottom: 1px solid #eee;'>"
                        f"<td style='padding: 8px;'><div style='width:16px; height:16px; border-radius:50%; background-color:{c_hex}; opacity:{op_style}; margin:auto;'></div></td>"
                        f"<td style='padding: 8px; text-align: left;'>{row_lote['Partida']}</td>"
                        f"<td style='padding: 8px; font-size: 11px; white-space: nowrap;'>{row_lote['Estatus']}</td>"
                        f"<td style='padding: 8px;'>${row_lote['Precio']:,.2f}</td>"
                        "</tr>"
                    )
                html_table += "</tbody></table></div>"
                st.markdown(html_table, unsafe_allow_html=True)
            else:
                msg = f"No hay partidas que coincidan con tus filtros en el lote {lote_puro_num}." if filtros_activos else f"No se encontraron partidas para el lote {lote_puro_num}."
                st.info(msg)

    with col_mapa:
        nombres_posibles = ["SVGsembrado.txt", "SVGsembrado_1_LOTE-Model.txt", "SVGsembrado.svg"]
        archivo_encontrado = None
        
        for nombre in nombres_posibles:
            if os.path.exists(nombre):
                archivo_encontrado = nombre
                break
                
        if archivo_encontrado:
            try:
                with open(archivo_encontrado, "r", encoding="utf-8") as f:
                    svg_content = f.read()

                try:
                    soup = BeautifulSoup(svg_content, "xml")
                except:
                    soup = BeautifulSoup(svg_content, "html.parser")
                    
                for path_elem in soup.find_all(['path', 'polygon']):
                    path_elem['fill-rule'] = "evenodd"
                    if 'style' in path_elem.attrs:
                        if 'fill-rule' not in path_elem['style']:
                            path_elem['style'] += ";fill-rule:evenodd;"
                    else:
                        path_elem['style'] = "fill-rule:evenodd;"

                def calcular_centro_poligono(elemento):
                    coords_x, coords_y = [], []
                    try:
                        if elemento.name in ['polygon', 'polyline']:
                            pts = re.findall(r'[-+]?(?:\d*\.\d+|\d+)', elemento.get('points', ''))
                            coords_x = [float(pts[i]) for i in range(0, len(pts), 2)]
                            coords_y = [float(pts[i+1]) for i in range(0, len(pts), 2)]
                        elif elemento.name == 'path':
                            pts = re.findall(r'[-+]?(?:\d*\.\d+|\d+)', elemento.get('d', ''))
                            if len(pts) >= 2:
                                coords_x = [float(pts[i]) for i in range(0, len(pts)-1, 2)]
                                coords_y = [float(pts[i+1]) for i in range(0, len(pts)-1, 2)]
                        
                        if coords_x and coords_y:
                            min_x, max_x = min(coords_x), max(coords_x)
                            min_y, max_y = min(coords_y), max(coords_y)
                            cx = (min_x + max_x) / 2.0
                            cy = (min_y + max_y) / 2.0
                            radio_disp = min(max_x - min_x, max_y - min_y) * 0.30 
                            return cx, cy, radio_disp
                    except:
                        pass
                    return None, None, None
                
                svg_tag = soup.find("svg")
                
                if svg_tag:
                    if not svg_tag.get('viewBox') and not svg_tag.get('viewbox'):
                        w_orig = str(svg_tag.get('width', '')).replace('px', '').replace('pt', '').strip()
                        h_orig = str(svg_tag.get('height', '')).replace('px', '').replace('pt', '').strip()
                        if w_orig and h_orig and w_orig.replace('.', '', 1).isdigit() and h_orig.replace('.', '', 1).isdigit():
                            svg_tag['viewBox'] = f"0 0 {float(w_orig)} {float(h_orig)}"

                svg_tag['width'] = "100%"
                svg_tag['height'] = "100%"
                
                if not svg_tag.get('preserveAspectRatio'):
                    svg_tag['preserveAspectRatio'] = "xMidYMid meet"
              
                        
                    defs = soup.find('defs')
                    if not defs:
                        defs = soup.new_tag('defs')
                        svg_tag.insert(0, defs)

                for item in lotes_datos_mapa:
                    id_lote = str(item["Lote_Id"])
                    hex_color = item["Hex"]
                    
                    id_busqueda = f"lote-{id_lote}" 
                    lote_path = soup.find(id=id_busqueda)
                    
                    if not lote_path:
                        lote_path = soup.find(id=id_lote) or soup.find(id=f"Lote-{int(id_lote):02d}")

                    if lote_path:
                        etiqueta_hover = lote_path.find('title')
                        if not etiqueta_hover:
                            etiqueta_hover = soup.new_tag('title')
                            lote_path.append(etiqueta_hover)
                        etiqueta_hover.string = f"Lote-{id_lote}"

                        df_lote_esferas = pd.DataFrame()
                        is_selected_lote = (not st.session_state.mostrar_todos_mapa) and (id_lote == str(st.session_state.lote_actual))
                        
                        if filtros_activos:
                            df_lote_match = df_filtered[df_filtered['Lote'].astype(str).str.strip() == id_lote]
                            if not df_lote_match.empty:
                                if st.session_state.mostrar_todos_mapa or is_selected_lote:
                                    colores_opacidades = []
                                    partidas_vistas = set()
                                    
                                    for _, row_match in df_lote_match.iterrows():
                                        p_name = row_match['Partida']
                                        if p_name not in partidas_vistas:
                                            partidas_vistas.add(p_name)
                                            op = 1.0 if row_match['Estado'] == 'Pagado' else 0.5
                                            c_hex_p = mapa_colores_partida.get(p_name, '#3B82F6')
                                            colores_opacidades.append((c_hex_p, op))
                                            
                                    colores_opacidades = colores_opacidades[:4]
                                    
                                    if len(colores_opacidades) == 1:
                                        c, op = colores_opacidades[0]
                                        if is_selected_lote:
                                            lote_path['style'] = f"fill:{c}; fill-opacity:{op}; stroke:#FFFF00; stroke-width:8; opacity:1.0;"
                                        else:
                                            lote_path['style'] = f"fill:{c}; fill-opacity:{op}; stroke:#000000; stroke-width:6; opacity:1.0;"
                                    elif len(colores_opacidades) > 1:
                                        id_grad = f"grad_{id_lote}"
                                        n_cols = len(colores_opacidades)

                                        angulo_rotacion = 0
                                        try:
                                            d_attr = lote_path.get('d', '')
                                            numeros = re.findall(r'[-+]?(?:\d*\.\d+|\d+)', d_attr)
                                            
                                            if len(numeros) >= 4:
                                                max_dist = 0
                                                best_dx, best_dy = 1, 0
                                                
                                                for idx in range(2, len(numeros)-1, 2):
                                                    dx = float(numeros[idx])
                                                    dy = float(numeros[idx+1])
                                                    dist = dx*dx + dy*dy
                                                    if dist > max_dist:
                                                        max_dist = dist
                                                        best_dx = dx
                                                        best_dy = dy
                                                
                                                if max_dist > 0:
                                                    angulo_rotacion = math.degrees(math.atan2(best_dy, best_dx))
                                        except Exception:
                                            pass
                                        
                                        grad = soup.new_tag("linearGradient", id=id_grad, x1="0%", y1="0%", x2="100%", y2="0%")
                                        grad['gradientTransform'] = f"rotate({angulo_rotacion}, 0.5, 0.5)"
                                        
                                        for i, (c, op) in enumerate(colores_opacidades):
                                            start_pct = (i / n_cols) * 100
                                            end_pct = ((i + 1) / n_cols) * 100
                                            
                                            stop1 = soup.new_tag("stop", offset=f"{start_pct}%")
                                            stop1['stop-color'] = c
                                            stop1['stop-opacity'] = str(op)
                                            
                                            stop2 = soup.new_tag("stop", offset=f"{end_pct}%")
                                            stop2['stop-color'] = c
                                            stop2['stop-opacity'] = str(op)
                                            
                                            grad.append(stop1)
                                            grad.append(stop2)
                                        
                                        if defs:
                                            defs.append(grad)
                                            
                                        if is_selected_lote:
                                            lote_path['style'] = f"fill:url(#{id_grad}); stroke:#FFFF00; stroke-width:8; opacity:1.0;"
                                        else:
                                            lote_path['style'] = f"fill:url(#{id_grad}); stroke:#000000; stroke-width:6; opacity:1.0;"

                                    df_lote_esferas = df_lote_match
                                else:
                                    lote_path['style'] = f"fill:#e5e7eb; fill-opacity:0.3; stroke:#000000; stroke-width:2; opacity:0.3;"
                            else:
                                lote_path['style'] = f"fill:#e5e7eb; fill-opacity:0.3; stroke:#000000; stroke-width:2; opacity:0.3;"
                        else:
                            if not st.session_state.mostrar_todos_mapa and not is_selected_lote:
                                lote_path['style'] = f"fill:{hex_color};stroke:#000000;stroke-width:2;opacity:0.2;"
                            else:
                                if is_selected_lote:
                                    lote_path['style'] = f"fill:{hex_color};stroke:#FFFF00;stroke-width:8;opacity:1.0;"
                                else:
                                    lote_path['style'] = f"fill:{hex_color};stroke:#000000;stroke-width:6;opacity:1.0;"
                                
                                if is_selected_lote:
                                    df_lote_esferas = df_compat[df_compat['Lote'].astype(str).str.strip() == id_lote]

                        if not df_lote_esferas.empty:
                            cx_auto, cy_auto, r_auto = calcular_centro_poligono(lote_path)
                            
                            if cx_auto is not None and cy_auto is not None:
                                base_x, base_y = cx_auto, cy_auto
                                radio_disp = max(r_auto, 5) 
                            else:
                                base_x = float(item["x"])
                                base_y = float(item["y"])
                                radio_disp = 12 
                            
                            num_esferas = len(df_lote_esferas)
                            r_esfera = 50 if num_esferas < 10 else 5
                            
                            for idx, row in enumerate(df_lote_esferas.itertuples()):
                                if num_esferas == 1:
                                    cx, cy = base_x, base_y
                                else:
                                    angulo = (2 * math.pi * idx) / num_esferas
                                    cx = base_x + radio_disp * math.cos(angulo)
                                    cy = base_y + radio_disp * math.sin(angulo)
                                
                                color_burbuja = mapa_colores_partida.get(row.Partida, "#3B82F6")
                                
                                if row.Estado == "Pagado":
                                    fill_style = color_burbuja
                                    fill_opacity = "1.0"
                                elif row.Estado == "Pago Parcial":
                                    fill_style = color_burbuja
                                    fill_opacity = "0.5"
                                else:
                                    fill_style = "none" 
                                    fill_opacity = "0.0"
                                    
                                if fill_opacity != "0.0":
                                    circle_tag = soup.new_tag(
                                        "circle", 
                                        cx=f"{cx:.2f}", 
                                        cy=f"{cy:.2f}", 
                                        r=str(r_esfera), 
                                        style=f"fill:{fill_style}; fill-opacity:{fill_opacity}; stroke:#1f2937; stroke-width:1px;"
                                    )
                                    lote_path.insert_after(circle_tag)

                html_final = str(soup).replace("viewbox=", "viewBox=")
                html_final = f"<div style='width:100%; height:1000px; display:flex; justify-content:center; align-items: center;'>{html_final}</div>"
                st.components.v1.html(html_final, height=1000, scrolling=False) 

            except Exception as e:
                st.error("⚠️ Hubo un problema al procesar el archivo SVG.")
                st.write(f"Detalle del error técnico: {e}")
        else:
            st.error("⚠️ No se encontró el archivo del mapa.")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("### 🔗 Diagrama Interactivo de Partidas")
    
    if st.session_state.mostrar_todos_mapa:
        st.info("⚠️ Selecciona un Lote específico desde el panel 'Desglose' (arriba a la derecha) para visualizar este diagrama.")
    else:
        df_lote_diag = df_compat[df_compat['Lote'].astype(str).str.strip() == str(st.session_state.lote_actual)]

        if not df_lote_diag.empty:
            num_partidas = len(df_lote_diag)
            cols = math.ceil(math.sqrt(num_partidas))

            filas = math.ceil(num_partidas / cols) if cols > 0 else 1
            
            x_coords, y_coords, colores_relleno, textos_hover = [], [], [], []

            ancho_celda = 10
            alto_celda = 5
            
            for i, row in enumerate(df_lote_diag.itertuples()):
                col_actual = i % cols
                fila_actual = i // cols
                
                x = (col_actual * ancho_celda) + (ancho_celda / 2.0)
                y = (fila_actual * alto_celda) + (alto_celda / 2.0)
                    
                x_coords.append(x)
                y_coords.append(y)

                estado = row.Estado
                costo = row.Precio
                pago_real = float(getattr(row, 'Pago_1', 0)) + float(getattr(row, 'Pago_2', 0))
                destajista = row.Destajista if pd.notna(row.Destajista) and row.Destajista != "" else "Sin Asignar"
                
                color_asignado = mapa_colores_partida.get(row.Partida, "#3B82F6")

                if estado == "Pagado":
                    colores_relleno.append(color_asignado)
                elif estado == "Pago Parcial":
                    colores_relleno.append(hex_to_rgba(color_asignado, 0.5))
                else:
                    colores_relleno.append("rgba(0,0,0,0)")

                hover_text = f"<b>Partida:</b> {row.Partida}<br><b>Costo Total:</b> ${costo:,.2f}<br><b>Pagado:</b> ${pago_real:,.2f}<br><b>Destajista:</b> {destajista}<br><b>Estado:</b> {estado}"
                textos_hover.append(hover_text)

            diametro_esfera_px = 60
            padding_px = 25 
            altura_grafico = max(350, filas * (diametro_esfera_px + padding_px))

            fig_diag = go.Figure(data=go.Scatter(
                x=x_coords,
                y=y_coords,
                mode='markers',
                marker=dict(
                    size=diametro_esfera_px, 
                    color=colores_relleno,
                    symbol='circle',
                    line=dict(width=0) 
                ),
                text=textos_hover,
                hoverinfo='text'
            ))

            x_min, y_min = 0.0, 0.0
            x_max = cols * ancho_celda
            y_max = filas * alto_celda
            
            fig_diag.add_shape(
                type="path",
                path=f"M {x_min} {y_min} L {x_min} {y_max} L {x_max} {y_max} L {x_max} {y_min} Z",
                line=dict(color="rgba(14,232,144,0.8)", width=8), 
                fillcolor="rgba(0,0,0,0)",
                layer="below"
            )
           
            prototipo_diag = df_lote_diag['Prototipo'].iloc[0] if not df_lote_diag.empty else "N/A"

            fig_diag.update_layout(
                title=dict(text=f"Esferas del Lote {st.session_state.lote_actual} – Prototipo {prototipo_diag}", font=dict(size=20)),
                xaxis=dict(visible=False, showgrid=False, zeroline=False),
                yaxis=dict(visible=False, showgrid=False, zeroline=False, autorange="reversed", scaleanchor="x", scaleratio=1),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                height=altura_grafico, 
                hoverlabel=dict(bgcolor="black", font_color="white", font_size=14, font_family="Arial") 
            )

            st.plotly_chart(fig_diag, use_container_width=True)
            
            pagadas_diag = len(df_lote_diag[df_lote_diag['Estado'] == 'Pagado'])
            pendientes_diag = num_partidas - pagadas_diag
            st.markdown(f"**🟢 Total Pagadas (100%):** {pagadas_diag} | **🔴 Pendientes/Parciales:** {pendientes_diag}")
            
        else:
            st.warning("⚠️ No hay partidas registradas para este lote.")