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
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode
from fpdf import FPDF
import base64

# --- OCULTAR BARRAS DE STREAMLIT ---
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    /* header {visibility: hidden;} Se elimina para permitir abrir/cerrar la barra lateral (Fix #12) */
    footer {visibility: hidden;}
    .stAppToolbar {visibility: hidden;}
    .stAppDeployButton {display: none;}
    </style>
    """,
    unsafe_allow_html=True
)
# -----------------------------------

# =========================================================================
# CONFIGURACIÓN INICIAL DE LA PÁGINA
# =========================================================================
st.set_page_config(page_title="ERP Destajos EGC", layout="wide")

URL_API_SHEET = st.secrets["URL_API_SHEET"] if "URL_API_SHEET" in st.secrets else ""

def obtener_datos_gsheet():
    try:
        response = requests.get(URL_API_SHEET)
        data = response.json()
        df = pd.DataFrame(data[1:], columns=data[0])

        # Asegurar que existan las nuevas columnas si la hoja está vacía o en transición
        columnas_requeridas = ['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', 'C.C', 'Pagar', 'Fecha pago', 'Usuario']
        for col in columnas_requeridas:
            if col not in df.columns:
                df[col] = ''

        # Formateos iniciales
        df['Costo'] = pd.to_numeric(df['Costo'], errors='coerce').fillna(0.0)
        df['Pagar'] = df['Pagar'].apply(lambda x: True if str(x).strip().upper() == 'TRUE' else False)
        
        # Guardamos el índice original para no perder la referencia al actualizar
        df['_IndexOriginal'] = df.index 

        return df
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        return pd.DataFrame()

def actualizar_datos_gsheet(df):
    try:
        # Preparamos el dataframe para enviar (sin la columna auxiliar de índice)
        df_a_enviar = df.drop(columns=['_IndexOriginal'], errors='ignore').copy()
        
        # Convertimos booleanos a strings para Google Sheets
        df_a_enviar['Pagar'] = df_a_enviar['Pagar'].astype(str).str.upper()
        
        datos_a_enviar = [df_a_enviar.columns.values.tolist()] + df_a_enviar.values.tolist()
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
    "CC-001 (Cimentación)",
    "CC-002 (Estructura)",
    "CC-003 (Acabados)",
    "CC-004 (Instalaciones Hidro)",
    "CC-005 (Instalaciones Elec)"
]

ANCHO_LOGIN_ENTRADAS = "200px"    
ESPACIO_ENTRE_RENGLONES = "8px"
TAMANO_LETRA_TABLA = "11px" 
TAMANO_LETRA_BOTONES = "12px"
COLOR_FONDO_PROTOTIPO = "#1E3A8A"
COLOR_TEXTO_PROTOTIPO = "#FFFFFF"

# --- CABECERA UNIVERSAL CON LOGO ---
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
# INICIALIZACIÓN DE ESTADOS (MEMORIA ABSOLUTA DEL SISTEMA)
# =========================================================================
if 'usuario' not in st.session_state:
    st.session_state.usuario = None

if 'df' not in st.session_state:
    st.session_state.df = obtener_datos_gsheet()
    st.session_state.df_original = st.session_state.df.copy()

df = st.session_state.df

# Función para extraer Estado (Para el mapa y dashboard)
def calcular_estado(pagar_val):
    return "Pagado" if pagar_val in [True, "TRUE", "True"] else "Pendiente"

# --- PALETA DE COLORES GLOBAL ---
partidas_unicas_global = df['Partida'].unique() if not df.empty else []
paleta_colores_global = px.colors.qualitative.Alphabet + px.colors.qualitative.Light24 + px.colors.qualitative.Dark24
mapa_colores_partida = {partida: paleta_colores_global[i % len(paleta_colores_global)] for i, partida in enumerate(partidas_unicas_global)}

if 'lote_actual' not in st.session_state:
    st.session_state.lote_actual = str(df['Lote'].unique()[0]) if not df.empty else "1"

if 'mostrar_todos_mapa' not in st.session_state:
    st.session_state.mostrar_todos_mapa = False

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

def sort_prototipo(val):
    v_limpio = str(val).replace("Prototipo", "").strip()
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', v_limpio)]

def sort_concepto(val):
    match = re.search(r'^(\d+)', str(val))
    num = int(match.group(1)) if match else 9999
    texto = re.sub(r'^\d+\.-\s*', '', str(val)).strip()
    return (num, texto)

# --- MENÚ DE NAVEGACIÓN LATERAL ---
st.sidebar.title(f"👷 {st.session_state.usuario}")
menu = st.sidebar.radio("Menú Principal:", [
    "Registro de Destajos", 
    "Dashboard (Gráficos y Visor)", 
    "Mapa Interactivo"
])

if 'menu_actual' not in st.session_state:
    st.session_state.menu_actual = menu

if st.session_state.menu_actual != menu:
    if menu == "Mapa Interactivo":
        st.session_state.mostrar_todos_mapa = True
    st.session_state.menu_actual = menu
    st.rerun()

st.sidebar.markdown("---")

# =========================================================================
# PESTAÑA 1: REGISTRO DE DESTAJOS
# =========================================================================
if menu == "Registro de Destajos":
    
    # 11. REPORTE PDF (Botón en Barra Lateral)
    if st.sidebar.button("📄 Generar Reporte PDF", type="secondary"):
        st.session_state.mostrar_modal_pdf = True

    if st.sidebar.button("💾 GUARDAR CAMBIOS", type="primary"):
        # Se captura el estado actual antes de guardar
        hubo_error = False
        cambios_realizados = 0
        ahora = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%d/%m/%Y %H:%M:%S")
        usuario_actual = st.session_state.usuario

        # Validaciones
        for idx, row in st.session_state.df.iterrows():
            if row['Pagar'] == True and str(row['Fecha pago']).strip() == '':
                # Si se marcó para pagar y no tiene fecha (es un pago nuevo)
                if str(row['Destajista']).strip() == '' or str(row['C.C']).strip() == '' or str(row['Destajista']).strip() == 'None' or str(row['C.C']).strip() == 'None':
                    hubo_error = True
                    break
        
        if hubo_error:
            st.sidebar.error("⚠️ Error: Hay partidas marcadas en 'Pagar' sin Destajista o C.C asignado. Revisa la tabla.")
        else:
            with st.spinner("Sincronizando con Google..."):
                for idx, row in st.session_state.df.iterrows():
                    if row['Pagar'] == True and str(row['Fecha pago']).strip() == '':
                        st.session_state.df.at[idx, 'Fecha pago'] = ahora
                        st.session_state.df.at[idx, 'Usuario'] = usuario_actual
                        cambios_realizados += 1
                
                if cambios_realizados > 0:
                    actualizar_datos_gsheet(st.session_state.df)
                    st.session_state.df_original = st.session_state.df.copy()
                    st.sidebar.success(f"¡{cambios_realizados} partidas guardadas con éxito!")
                else:
                    st.sidebar.info("No se detectaron partidas nuevas por pagar.")
                st.rerun()

    if st.sidebar.button("🔒 Cerrar Sesión"):
        st.session_state.usuario = None
        st.rerun()

    mostrar_cabecera_con_logo("📝 Control de Pagos Destajos")

    # MODAL REPORTE PDF
    if st.session_state.get('mostrar_modal_pdf', False):
        st.markdown("### 🖨️ Configuración de Reporte PDF")
        col_f1, col_f2 = st.columns(2)
        fecha_inicio = col_f1.date_input("Fecha Inicio")
        fecha_fin = col_f2.date_input("Fecha Fin")
        
        if st.button("Descargar Reporte PDF"):
            # Lógica para PDF
            try:
                # Filtrar DF (Asumiendo que 'Fecha pago' tiene formato '%d/%m/%Y %H:%M:%S')
                df_rep = st.session_state.df.copy()
                df_rep = df_rep[df_rep['Fecha pago'].astype(str).str.strip() != '']
                df_rep['Fecha_dt'] = pd.to_datetime(df_rep['Fecha pago'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                
                mask = (df_rep['Fecha_dt'].dt.date >= fecha_inicio) & (df_rep['Fecha_dt'].dt.date <= fecha_fin)
                df_filtrado_pdf = df_rep.loc[mask]
                
                # Agrupar
                resumen_pdf = df_filtrado_pdf.groupby(['Destajista', 'C.C'])['Costo'].sum().reset_index()
                
                # Crear PDF
                pdf = FPDF(orientation='P', unit='mm', format='Letter')
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(200, 10, txt="Reporte de Pagos por Destajista y C.C", ln=True, align='C')
                pdf.set_font("Arial", '', 12)
                pdf.cell(200, 10, txt=f"Periodo: {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}", ln=True, align='C')
                pdf.ln(10)
                
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(80, 10, "Destajista", 1)
                pdf.cell(70, 10, "Centro de Costo (C.C)", 1)
                pdf.cell(40, 10, "Cantidad Pagada", 1, ln=True)
                
                pdf.set_font("Arial", '', 10)
                total_general = 0
                for _, row_pdf in resumen_pdf.iterrows():
                    pdf.cell(80, 10, str(row_pdf['Destajista'])[:40], 1)
                    pdf.cell(70, 10, str(row_pdf['C.C'])[:35], 1)
                    pdf.cell(40, 10, f"${row_pdf['Costo']:,.2f}", 1, ln=True)
                    total_general += float(row_pdf['Costo'])
                
                pdf.ln(5)
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(150, 10, "Total Pagado en el Periodo:", 0, 0, 'R')
                pdf.cell(40, 10, f"${total_general:,.2f}", 0, 1, 'L')
                
                # Generar archivo en memoria
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                b64 = base64.b64encode(pdf_bytes).decode()
                
                href = f'<a href="data:application/pdf;base64,{b64}" download="Reporte_{fecha_inicio}_al_{fecha_fin}.pdf" target="_blank" style="background-color:#3B82F6; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">📥 Haz clic aquí para guardar/imprimir el PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"Error al generar PDF: {e}")
                
        if st.button("Cerrar Modal"):
            st.session_state.mostrar_modal_pdf = False
            st.rerun()
        
        st.markdown("---")

    # --- 1. RESUMEN ENCABEZADO LOTE - PROTOTIPO ---
    lotes_disponibles = sorted(list(df['Lote'].astype(str).unique()), key=clave_ordenamiento)
    lote_display = st.session_state.get('filtro_lotes', lotes_disponibles)
    
    if lote_display:
        df_encabezado = df[df['Lote'].astype(str).isin(lote_display)]
        prototipos_encabezado = ", ".join(df_encabezado['Prototipo'].astype(str).unique())
        costo_total_filtrado = df_encabezado['Costo'].sum()
        
        st.markdown(f"""
        <div style="background-color:{COLOR_FONDO_PROTOTIPO}; padding:20px; border-radius:10px; margin-bottom:20px; color:{COLOR_TEXTO_PROTOTIPO}; text-align:center;">
            <div style="font-size:24px; font-weight:bold; margin-bottom: 5px;">🏠 Lote(s): {', '.join(lote_display)}</div>
            <div style="font-size:18px; margin-bottom: 5px;">Prototipo(s): {prototipos_encabezado}</div>
            <div style="font-size:16px; opacity:0.9;">Costo Total Estimado: ${costo_total_filtrado:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    # --- 2. FILTROS DE TABLA (CRUZADOS) ---
    st.markdown("##### ⏳ Filtros de Tabla")
    
    if st.button("🔄 Limpiar todos los filtros"):
        keys_to_clear = ['filtro_proto', 'filtro_mz', 'filtro_lotes', 'filtro_estado', 'filtro_fecha', 'filtro_conc', 'filtro_dest']
        for k in keys_to_clear:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

    col_f1, col_f2, col_f3, col_f4, col_f5, col_f6 = st.columns([1.5, 1.5, 2, 1.5, 2, 2])
    
    # Preparación de datos para filtros
    df_f = df.copy()
    
    # Prototipo (Formateo y Orden)
    df_f['Proto_Format'] = df_f['Prototipo'].apply(lambda x: f"Prototipo {x}" if "Prototipo" not in str(x) else str(x))
    protos_unicos = sorted(df_f['Proto_Format'].unique(), key=sort_prototipo)
    
    # Manzana
    mz_unicos = sorted(df_f['Manzana'].dropna().astype(str).unique(), key=clave_ordenamiento)
    
    # Conceptos (Partida)
    conceptos_unicos = sorted(df_f['Partida'].dropna().unique(), key=sort_concepto)
    # Remover numero para visualización en el selectbox
    conceptos_display = [re.sub(r'^\d+\.-\s*', '', str(c)).strip() for c in conceptos_unicos]
    dict_conceptos = dict(zip(conceptos_display, conceptos_unicos)) # Mapeo inverso

    # Destajistas
    dest_unicos = sorted([d for d in df_f['Destajista'].unique() if str(d).strip() != ''], key=clave_ordenamiento)

    # UI Filtros
    f_proto = col_f1.selectbox("Prototipo:", ["Mostrar todos"] + protos_unicos, key="filtro_proto")
    f_mz = col_f2.selectbox("Manzana:", ["Mostrar todos"] + mz_unicos, key="filtro_mz")
    f_lotes = col_f3.multiselect("Lote(s):", options=lotes_disponibles, default=st.session_state.get('filtro_lotes', []), key="filtro_lotes")
    f_concepto_disp = col_f4.selectbox("Concepto:", ["Mostrar todos"] + conceptos_display, key="filtro_conc")
    f_dest = col_f5.selectbox("Destajista:", ["Mostrar todos"] + dest_unicos, key="filtro_dest")
    f_estado = col_f6.selectbox("Estado de Pago:", ["Mostrar todos", "Pagado", "Pendiente"], key="filtro_estado")
    f_fecha = st.date_input("Filtrar por Rango de Fecha:", value=None, key="filtro_fecha") # Rango devuelve una tupla de 2

    # Aplicar Filtros
    df_filtrado = df_f.copy()
    
    if f_proto != "Mostrar todos":
        df_filtrado = df_filtrado[df_filtrado['Proto_Format'] == f_proto]
    if f_mz != "Mostrar todos":
        df_filtrado = df_filtrado[df_filtrado['Manzana'].astype(str) == f_mz]
    if f_lotes:
        df_filtrado = df_filtrado[df_filtrado['Lote'].astype(str).isin(f_lotes)]
    if f_concepto_disp != "Mostrar todos":
        df_filtrado = df_filtrado[df_filtrado['Partida'] == dict_conceptos[f_concepto_disp]]
    if f_dest != "Mostrar todos":
        df_filtrado = df_filtrado[df_filtrado['Destajista'] == f_dest]
    if f_estado != "Mostrar todos":
        bool_estado = True if f_estado == "Pagado" else False
        df_filtrado = df_filtrado[df_filtrado['Pagar'] == bool_estado]
    
    if isinstance(f_fecha, tuple) and len(f_fecha) == 2:
        # Asumiendo que 'Fecha pago' tiene formato 'dd/mm/yyyy hh:mm:ss'
        df_filtrado['Fecha_temp'] = pd.to_datetime(df_filtrado['Fecha pago'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date
        df_filtrado = df_filtrado[(df_filtrado['Fecha_temp'] >= f_fecha[0]) & (df_filtrado['Fecha_temp'] <= f_fecha[1])]
        df_filtrado.drop(columns=['Fecha_temp'], inplace=True)

    # Eliminar columna formato temporal
    df_filtrado.drop(columns=['Proto_Format'], inplace=True, errors='ignore')

    # --- 8 y 9. SUMATORIAS EN TIEMPO REAL ---
    # La suma "Costo" dinámica se calcula basada en las celdas marcadas.
    # Dado que Streamlit AgGrid devuelve el DataFrame modificado, usamos session_state temporal o recalculamos.
    
    # Filtramos las columnas exactas solicitadas
    columnas_tabla = ['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', 'C.C', 'Pagar', 'Fecha pago', 'Usuario', '_IndexOriginal']
    df_tabla = df_filtrado[columnas_tabla].copy()

    # --- 10. ASIGNACIONES MASIVAS y 19. CHECKBOXES MASIVOS ---
    st.markdown("<br>", unsafe_allow_html=True)
    c_masivo1, c_masivo2, c_masivo3, c_masivo4 = st.columns(4)
    
    # Selectores temporales para masivos
    dest_masivo = c_masivo1.selectbox("Destajista Masivo", ["Seleccionar..."] + LISTA_DESTAJISTAS, label_visibility="collapsed")
    if c_masivo1.button("Asignar Destajista Masivo", use_container_width=True):
        if dest_masivo != "Seleccionar...":
            for idx in df_tabla['_IndexOriginal']:
                if st.session_state.df.at[idx, 'Fecha pago'] == '': # Solo editar si no está pagado
                    st.session_state.df.at[idx, 'Destajista'] = dest_masivo
            st.rerun()

    cc_masivo = c_masivo2.selectbox("C.C Masivo", ["Seleccionar..."] + LISTA_CC, label_visibility="collapsed")
    if c_masivo2.button("Asignar C.C Masivo", use_container_width=True):
        if cc_masivo != "Seleccionar...":
            for idx in df_tabla['_IndexOriginal']:
                if st.session_state.df.at[idx, 'Fecha pago'] == '':
                    st.session_state.df.at[idx, 'C.C'] = cc_masivo
            st.rerun()

    # Seleccionar / Deseleccionar Todos
    c_masivo3.markdown("<br>", unsafe_allow_html=True)
    if c_masivo3.button("✅ Seleccionar Todos", use_container_width=True):
        for idx in df_tabla['_IndexOriginal']:
            if st.session_state.df.at[idx, 'Fecha pago'] == '': # Proteger los ya pagados
                st.session_state.df.at[idx, 'Pagar'] = True
        st.rerun()
        
    c_masivo4.markdown("<br>", unsafe_allow_html=True)
    if c_masivo4.button("⬜ Seleccionar Ninguno", use_container_width=True):
        for idx in df_tabla['_IndexOriginal']:
            if st.session_state.df.at[idx, 'Fecha pago'] == '':
                st.session_state.df.at[idx, 'Pagar'] = False
        st.rerun()

    # --- CONFIGURACIÓN DE AGGRID ---
    # Aplicar regla: Si costo es 0, no se puede pagar (o en AgGrid no lo permitimos/visualizamos igual)
    # Sin embargo la instrucción pide colocar "N/A" si es 0, al ser booleano lo desactivamos por seguridad.
    
    # Renderizamos la tabla usando AgGrid para permitir edición inline rica y estilos por fila
    gd = GridOptionsBuilder.from_dataframe(df_tabla)
    
    # Configuración de columnas
    gd.configure_column('_IndexOriginal', hide=True)
    gd.configure_columns(['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Fecha pago', 'Usuario'], editable=False)
    
    # Formato Moneda
    gd.configure_column('Costo', valueFormatter="x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})", type=["numericColumn"])
    
    # Dropdowns Editables
    gd.configure_column('Destajista', editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': LISTA_DESTAJISTAS})
    gd.configure_column('C.C', editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': LISTA_CC})
    
    # Checkbox de pago
    gd.configure_column('Pagar', editable=True, cellRenderer='agCheckboxCellRenderer', cellEditor='agCheckboxCellEditor')

    # Deshabilitar ordenamiento de cabecera como se solicitó
    gd.configure_default_column(sortable=False, filter=False, cellStyle={'textAlign': 'center'})
    gd.configure_column('Partida', cellStyle={'textAlign': 'left'}) # Mejor lectura
    
    # Inyección de código JS para dar formato a la fila bloqueada (Gris) y Normal (Negro/Verde)
    jscode_row_style = JsCode("""
    function(params) {
        if (params.data['Fecha pago'] !== null && params.data['Fecha pago'] !== '') {
            return {
                'color': '#888888',
                'backgroundColor': '#2A2A2A',
                'pointerEvents': 'none'
            };
        }
        return {
            'color': '#39FF14',
            'backgroundColor': 'black'
        };
    }
    """)
    gd.configure_grid_options(getRowStyle=jscode_row_style)

    gridOptions = gd.build()

    # Etiquetas de suma en tiempo real (Calculadas a partir del DataFrame principal que Streamlit conoce)
    # Costo = Suma de Costo de partidas "Pagar" = True y "Fecha pago" == '' (Las que se están por guardar)
    # Pagos = Suma de Costo de partidas "Pagar" = True y "Fecha pago" != '' (Las ya guardadas)
    
    costo_a_pagar = df_tabla[(df_tabla['Pagar'] == True) & (df_tabla['Fecha pago'] == '')]['Costo'].sum()
    total_pagos_historicos = df_tabla[(df_tabla['Pagar'] == True) & (df_tabla['Fecha pago'] != '')]['Costo'].sum()
    
    st.markdown(f"""
    <div style='display:flex; justify-content:space-between; align-items:center; background-color:#1E1E1E; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #3B82F6;'>
        <div style='font-size: 20px; font-weight: bold; color: #39FF14;'>💸 Monto Actual por Pagar: ${costo_a_pagar:,.2f}</div>
        <div style='font-size: 16px; font-weight: bold; color: #3B82F6;'>🔹 Pagos (Realizados en tabla): ${total_pagos_historicos:,.2f}</div>
    </div>
    """, unsafe_allow_html=True)

    # Inyección CSS general para AgGrid y la pantalla
    st.markdown("""
        <style>
            .ag-header-cell-label { justify-content: center; }
            .ag-theme-streamlit { --ag-header-background-color: black; --ag-header-foreground-color: white; --ag-row-border-color: lightgray; }
        </style>
    """, unsafe_allow_html=True)

    # Render de la tabla
    grid_response = AgGrid(
        df_tabla,
        gridOptions=gridOptions,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.AS_INPUT,
        allow_unsafe_jscode=True,
        theme='streamlit',
        height=600,
        fit_columns_on_grid_load=True
    )

    # Actualizar sesión con los cambios hechos en AgGrid en tiempo real
    if grid_response['data'] is not None:
        df_editado = grid_response['data']
        cambio_detectado = False
        
        for idx_row, row_editada in df_editado.iterrows():
            idx_original = row_editada['_IndexOriginal']
            
            # Solo actualizar si no está bloqueado (Fecha pago vacía)
            if st.session_state.df.at[idx_original, 'Fecha pago'] == '':
                # Actualizar Pagar
                if st.session_state.df.at[idx_original, 'Pagar'] != row_editada['Pagar']:
                    # Regla de Costo 0 = N/A -> No permitir Pagar
                    if row_editada['Pagar'] == True and float(row_editada['Costo']) == 0.0:
                        st.warning(f"No se puede pagar la partida '{row_editada['Partida']}' porque su costo es 0.")
                        st.session_state.df.at[idx_original, 'Pagar'] = False
                    else:
                        st.session_state.df.at[idx_original, 'Pagar'] = row_editada['Pagar']
                        cambio_detectado = True
                
                # Actualizar Destajista
                if st.session_state.df.at[idx_original, 'Destajista'] != row_editada['Destajista']:
                    st.session_state.df.at[idx_original, 'Destajista'] = row_editada['Destajista']
                    cambio_detectado = True
                    
                # Actualizar C.C
                if st.session_state.df.at[idx_original, 'C.C'] != row_editada['C.C']:
                    st.session_state.df.at[idx_original, 'C.C'] = row_editada['C.C']
                    cambio_detectado = True

        if cambio_detectado:
            st.rerun() # Fuerza la actualización de las sumatorias en la cabecera

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
    protos_disponibles = sorted(df['Prototipo'].unique(), key=ordenar_prototipos)
    lotes_disponibles = list(df['Lote'].unique())
    destajistas_disponibles = ["Todos"] + list(df['Destajista'].dropna().unique())
    
    if 'tab2_lotes_seleccionados' not in st.session_state:
        st.session_state.tab2_lotes_seleccionados = lotes_disponibles
        
    protos_dash = d_col1.multiselect("Filtrar por Prototipos:", options=protos_disponibles, default=protos_disponibles)
    lotes_dash = d_col2.multiselect("Filtrar por Lotes:", options=lotes_disponibles, key="tab2_lotes_seleccionados")
    destajista_dash = d_col3.selectbox("Filtrar por Destajista Global:", options=destajistas_disponibles)
    
    df_dash = df[(df['Lote'].isin(lotes_dash)) & (df['Prototipo'].isin(protos_dash))].copy()
    if destajista_dash != "Todos":
        df_dash = df_dash[df_dash['Destajista'] == destajista_dash]
    
    if df_dash.empty:
        st.warning("⚠️ No hay datos para mostrar con los filtros seleccionados.")
    else:
        # Adaptación a la nueva estructura: El pagado real depende de si Pagar es True
        df_dash['Total_Pagado_Real'] = df_dash.apply(lambda x: float(x['Costo']) if x['Pagar'] else 0.0, axis=1)
        df_dash['Estado'] = df_dash['Pagar'].apply(calcular_estado)
        
        monto_total = df_dash['Costo'].sum()
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
        df_dash_clean['Deuda_Pendiente'] = df_dash_clean['Costo'] - df_dash_clean['Total_Pagado_Real']
        
        df_resumen = df_dash_clean.groupby(['Lote', 'Prototipo'])[['Costo', 'Total_Pagado_Real', 'Deuda_Pendiente']].sum().reset_index()
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
            
            df_proto_graf = df_dash.groupby(['Prototipo', 'Estado'])['Costo'].sum().reset_index()
            fig_proto = px.bar(df_proto_graf, x='Prototipo', y='Costo', color='Estado', 
                               title="Comportamiento Financiero por Prototipo",
                               barmode='group', text_auto='.2s',
                               color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#EF4444'})
            fig_proto.update_traces(textposition='outside')
            g_col1.plotly_chart(fig_proto, use_container_width=True)
            
            fig_tree = px.treemap(df_dash, path=[px.Constant("Proyecto EGC"), 'Prototipo', 'Lote', 'Estado'], values='Costo',
                                  title="Distribución del Presupuesto (Clic para explorar)",
                                  color='Estado', color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#EF4444', '(?)': '#cbd5e1'})
            fig_tree.update_traces(root_color="lightgrey")
            fig_tree.update_layout(margin=dict(t=50, l=25, r=25, b=25))
            g_col2.plotly_chart(fig_tree, use_container_width=True)
            
            df_lotes_graf = df_dash.groupby(['Lote', 'Estado'])['Costo'].sum().reset_index()
            fig_lote = px.bar(df_lotes_graf, x='Lote', y='Costo', color='Estado', 
                              title="Avance Financiero Específico por Lote",
                              color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#EF4444'})
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
                
            df_deudores = df_dash[df_dash['Total_Pagado_Real'] < df_dash['Costo']].copy()
            if not df_deudores.empty:
                df_deudores['Deuda'] = df_deudores['Costo'] - df_deudores['Total_Pagado_Real']
                df_deudores_clean = df_deudores.fillna("Sin Asignar")
                df_deuda = df_deudores_clean.groupby('Destajista')['Deuda'].sum().reset_index().sort_values('Deuda', ascending=True)
                fig_deuda = px.bar(df_deuda, y='Destajista', x='Deuda', orientation='h',
                                   title="🚨 Pagos Pendientes por Destajista (Deuda Restante)",
                                   color_discrete_sequence=['#EF4444'], text_auto='$.2s')
                g_col4.plotly_chart(fig_deuda, use_container_width=True)
            else:
                g_col4.success("¡Excelente! No hay deuda pendiente para la selección actual.")

# =========================================================================
# PESTAÑA 3: MAPA INTERACTIVO (CON INTEGRACIÓN SVG Y ESFERAS INYECTADAS)
# =========================================================================
elif menu == "Mapa Interactivo":
    mostrar_cabecera_con_logo("🗺️ Plano Interactivo Dinámico", "Visualización gráfica del avance del desarrollo.")

    def hex_to_rgba(hex_val, opacity):
        hex_val = hex_val.lstrip('#')
        if len(hex_val) == 6:
            return f"rgba({int(hex_val[0:2], 16)}, {int(hex_val[2:4], 16)}, {int(hex_val[4:6], 16)}, {opacity})"
        return "rgba(0,0,0,0)"

    # --- ARCHIVO DE COORDENADAS INTERNO ---
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

    # Asignar 'Estado' y 'Total_Pagado_Real' basado en Pagar
    df['Total_Pagado_Real'] = df.apply(lambda x: float(x['Costo']) if x['Pagar'] else 0.0, axis=1)
    df['Estado'] = df['Pagar'].apply(calcular_estado)

    lotes_datos_mapa = []
    for lote_num, coords in COORDENADAS_LOTES.items():
        df_lote_mapa = df[df['Lote'].astype(str).str.strip() == str(lote_num)].copy()
        
        if not df_lote_mapa.empty:
            total_partidas = len(df_lote_mapa)
            total_precio_lote = df_lote_mapa['Costo'].sum()
            total_pagado_lote = df_lote_mapa['Total_Pagado_Real'].sum()
            
            porcentaje = (total_pagado_lote / total_precio_lote * 100) if total_precio_lote > 0 else 0
            pagadas_completas = len(df_lote_mapa[df_lote_mapa['Estado'] == 'Pagado'])
            
            # --- LÓGICA DE ETAPAS DE OBRA ---
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
            else: # Mayor a 95% hasta 100%
                color_lote = "🟢 Detallado y entrega"
                hex_color = "#10B981"      # Verde
            # --------------------------------------
                
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
        df_kpi = df.copy()
        titulo_kpi = "🏠 Proyecto General (Todos los Lotes)"
    else:
        lote_puro_kpi = str(st.session_state.lote_actual)
        df_kpi = df[df['Lote'].astype(str).str.strip() == lote_puro_kpi].copy()
        
        prototipo_kpi = df_kpi['Prototipo'].iloc[0] if not df_kpi.empty else "N/A"
        titulo_kpi = f"🏠 Lote {lote_puro_kpi} - Prototipo {prototipo_kpi}"
        
    costo_total_mapa = df_kpi['Costo'].sum()
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
    for p in df['Partida'].dropna().unique():
        if str(p).strip() and str(p) not in partidas_ordenadas:
            partidas_ordenadas.append(str(p))
            
    partidas_display = [f"{i}.- {p}" for i, p in enumerate(partidas_ordenadas, start=1)]
    destajistas_unicos_filtro = sorted([str(d) for d in df['Destajista'].dropna().unique() if str(d).strip()], key=clave_ordenamiento)
    
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
    
    df_filtered = df[df['Estado'].isin(['Pagado'])].copy()
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

            mapa_sel = st.selectbox("Selector", opciones_selector, index=idx_t3, label_visibility="collapsed")
                
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
                        "<tr><th style='padding: 10px; border-bottom: 2px solid #ddd;'></th><th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left;'>Lote</th><th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left;'>Partida</th><th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left;'>Destajista</th></tr></thead><tbody>"
                    )
                    
                    for _, row_lote in df_filtered.iterrows():
                        c_hex = mapa_colores_partida.get(row_lote['Partida'], '#3B82F6')
                        destajista_str = row_lote['Destajista'] if pd.notna(row_lote['Destajista']) and row_lote['Destajista'] != "" else "Sin Asignar"
                        
                        html_table += (
                            f"<tr style='border-bottom: 1px solid #eee;'><td style='padding: 8px;'><div style='width:16px; height:16px; border-radius:50%; background-color:{c_hex}; opacity:1.0; margin:auto;'></div></td>"
                            f"<td style='padding: 8px; text-align: left;'>{row_lote['Lote']}</td><td style='padding: 8px; text-align: left;'>{row_lote['Partida']}</td><td style='padding: 8px; text-align: left;'>{destajista_str}</td></tr>"
                        )
                    html_table += "</tbody></table></div>"
                    st.markdown(html_table, unsafe_allow_html=True)
                else:
                    st.info("No se encontraron partidas con avance que coincidan con los filtros seleccionados.")
            else:
                st.markdown("**Resumen General por Lote (Financiero):**")
                df_resumen_global = df.copy()
                
                df_resumen_global_grp = df_resumen_global.groupby('Lote').agg(
                    Total_Partidas=('Partida', 'count'),
                    Pagadas=('Estado', lambda x: (x == 'Pagado').sum()),
                    Costo_Total=('Costo', 'sum'),
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
                df_desglose_lote = df_filtered[df_filtered['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Costo']].copy()
            else:
                st.markdown(f"**Desglose General (Lote {lote_puro_num}):**")
                df_desglose_lote = df[df['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Costo']].copy()
            
            if not df_desglose_lote.empty:
                def formatear_estado_icono(val):
                    if val == "Pagado": return "🟢 100% PAGADO"
                    return "🔴 PENDIENTE"
                    
                df_desglose_lote['Estatus'] = df_desglose_lote['Estado'].apply(formatear_estado_icono)
                
                html_table = (
                    "<div style='height: 700px; overflow-y: auto; font-family: sans-serif; font-size: 14px; width: 100%'>" 
                    "<table style='width: 100%; border-collapse: collapse; text-align: center; color: #d1d1d1;'>" 
                    "<thead style='position: sticky; top: 0; background-color: #262626; z-index: 10;'>" 
                    "<tr><th style='padding: 10px; border-bottom: 2px solid #ddd;'></th><th style='padding: 10px; border-bottom: 2px solid #ddd; text-align: left; '>Partida</th><th style='padding: 10px; border-bottom: 2px solid #ddd;'>Estatus</th><th style='padding: 10px; border-bottom: 2px solid #ddd;'>Costo</th></tr></thead><tbody>"
                )
                
                for _, row_lote in df_desglose_lote.iterrows():
                    c_hex = mapa_colores_partida.get(row_lote['Partida'], '#3B82F6')
                    op_style = "1.0" if row_lote['Estado'] == 'Pagado' else "0.3"

                    html_table += (
                        f"<tr style='border-bottom: 1px solid #eee;'><td style='padding: 8px;'><div style='width:16px; height:16px; border-radius:50%; background-color:{c_hex}; opacity:{op_style}; margin:auto;'></div></td>"
                        f"<td style='padding: 8px; text-align: left;'>{row_lote['Partida']}</td><td style='padding: 8px; font-size: 11px; white-space: nowrap;'>{row_lote['Estatus']}</td><td style='padding: 8px;'>${row_lote['Costo']:,.2f}</td></tr>"
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
                                    df_lote_esferas = df[df['Lote'].astype(str).str.strip() == id_lote]

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
                                else:
                                    fill_style = "none" 
                                    fill_opacity = "0.0"
                                    
                                if fill_opacity != "0.0":
                                    circle_tag = soup.new_tag(
                                        "circle", cx=f"{cx:.2f}", cy=f"{cy:.2f}", r=str(r_esfera), 
                                        style=f"fill:{fill_style}; fill-opacity:{fill_opacity}; stroke:#1f2937; stroke-width:1px;"
                                    )
                                    lote_path.insert_after(circle_tag)

                html_final = str(soup).replace("viewbox=", "viewBox=")
                html_final = f"<div style='width:100%; height:1000px; display:flex; justify-content:center; align-items: center;'>{html_final}</div>"
                st.components.v1.html(html_final, height=1000, scrolling=False)

            except Exception as e:
                st.error("⚠️ Hubo un problema al procesar el archivo SVG.")
        else:
            st.error("⚠️ No se encontró el archivo del mapa.")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("### 🔗 Diagrama Interactivo de Partidas")
    
    if st.session_state.mostrar_todos_mapa:
        st.info("⚠️ Selecciona un Lote específico desde el panel 'Desglose' para visualizar este diagrama.")
    else:
        df_lote_diag = df[df['Lote'].astype(str).str.strip() == str(st.session_state.lote_actual)]

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
                costo = float(row.Costo)
                destajista = row.Destajista if pd.notna(row.Destajista) and str(row.Destajista).strip() != "" else "Sin Asignar"
                color_asignado = mapa_colores_partida.get(row.Partida, "#3B82F6")

                if estado == "Pagado":
                    colores_relleno.append(color_asignado)
                else:
                    colores_relleno.append("rgba(0,0,0,0)")

                hover_text = f"<b>Partida:</b> {row.Partida}<br><b>Costo:</b> ${costo:,.2f}<br><b>Destajista:</b> {destajista}<br><b>Estado:</b> {estado}"
                textos_hover.append(hover_text)

            diametro_esfera_px = 60
            padding_px = 25 
            altura_grafico = max(350, filas * (diametro_esfera_px + padding_px))

            fig_diag = go.Figure(data=go.Scatter(
                x=x_coords, y=y_coords, mode='markers',
                marker=dict(size=diametro_esfera_px, color=colores_relleno, symbol='circle', line=dict(width=0)),
                text=textos_hover, hoverinfo='text'
            ))

            x_min, y_min = 0.0, 0.0
            x_max = cols * ancho_celda
            y_max = filas * alto_celda

            fig_diag.add_shape(
                type="path",
                path=f"M {x_min} {y_min} L {x_min} {y_max} L {x_max} {y_max} L {x_max} {y_min} Z",
                line=dict(color="rgba(14,232,144,0.8)", width=8), 
                fillcolor="rgba(0,0,0,0)", layer="below"
            )
            
            prototipo_diag = df_lote_diag['Prototipo'].iloc[0] if not df_lote_diag.empty else "N/A"

            fig_diag.update_layout(
                title=dict(text=f"Esferas del Lote {st.session_state.lote_actual} – Prototipo {prototipo_diag}", font=dict(size=20)),
                xaxis=dict(visible=False, showgrid=False, zeroline=False),
                yaxis=dict(visible=False, showgrid=False, zeroline=False, autorange="reversed", scaleanchor="x", scaleratio=1),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                height=altura_grafico, 
                hoverlabel=dict(bgcolor="black", font_color="white", font_size=14, font_family="Arial") 
            )

            st.plotly_chart(fig_diag, use_container_width=True)
            
            pagadas_diag = len(df_lote_diag[df_lote_diag['Estado'] == 'Pagado'])
            pendientes_diag = num_partidas - pagadas_diag
            st.markdown(f"**🟢 Total Pagadas (100%):** {pagadas_diag} | **🔴 Pendientes:** {pendientes_diag}")