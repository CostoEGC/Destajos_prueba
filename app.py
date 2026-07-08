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
import tempfile

# --- OCULTAR BARRAS DE STREAMLIT ---
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
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

        cols_requeridas = ['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', 'C.C', 'Pagar', 'Fecha pago', 'Usuario']
        for col in cols_requeridas:
            if col not in df.columns:
                df[col] = ''

        # (Corrección 1) Limpieza absoluta de la Fecha para evitar que se bloqueen celdas por falsos positivos ('nan')
        df['Fecha pago'] = df['Fecha pago'].astype(str).replace(['nan', 'NaN', 'None', 'NaT', 'null', '<NA>'], '')
        
        df['Costo'] = pd.to_numeric(df['Costo'], errors='coerce').fillna(0)
        df['Pagar'] = df['Pagar'].astype(str).str.lower().isin(['true', '1', 'sí', 'si', 'x', 'checked'])
        df['Prototipo'] = df['Prototipo'].apply(lambda x: f"Prototipo {x}" if "Prototipo" not in str(x) else x)

        return df[cols_requeridas] 
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        return pd.DataFrame()

def actualizar_datos_gsheet(df):
    try:
        datos_a_enviar = [df.columns.values.tolist()] + df.values.tolist()
        response = requests.post(URL_API_SHEET, json=datos_a_enviar)
        if response.status_code != 200:
            st.error("⚠️ Hubo un problema al guardar en la nube.")
    except Exception as e:
        st.error(f"Error al enviar datos a Google Sheets: {e}")

# =========================================================================
# ⚙️ CONFIGURACIÓN DE DISEÑO Y VARIABLES GLOBALES
# =========================================================================
LISTA_DESTAJISTAS = [
    " ",
    "Pablo Barragán (Albañilería)",
    "Andrés (Albañilería)",
    "Miguel Leyva (Instalaciones)",
    "José López (Pisos)",
    "Guillermo (Pintura)",
    "Gerardo Zamora (Yeso y pintura)"
]

LISTA_CC = [
    " ",
    "N62",
    "N75",
    "F13",
    "S03",
    "R01"
]

ANCHO_LOGIN_ENTRADAS = "200px"    
COLOR_FONDO_PROTOTIPO = "#1E3A8A"
COLOR_TEXTO_PROTOTIPO = "#FFFFFF"

def mostrar_cabecera_con_logo(titulo, subtitulo=None):
    col_texto, col_logo = st.columns([8, 2])
    with col_texto:
        st.title(titulo)
        if subtitulo:
            st.write(subtitulo)
    with col_logo:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)

def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(_nsre, str(s))]

def sort_conceptos(s):
    match = re.search(r'^\d+', str(s))
    num = int(match.group()) if match else 9999
    return num

# =========================================================================
# INICIALIZACIÓN DE ESTADOS (MEMORIA ABSOLUTA DEL SISTEMA)
# =========================================================================
if 'usuario' not in st.session_state: st.session_state.usuario = None
if 'df' not in st.session_state:
    st.session_state.df = obtener_datos_gsheet()
    st.session_state.df_original = st.session_state.df.copy()

if 'grid_key' not in st.session_state: st.session_state.grid_key = 0
if 'current_grid_state' not in st.session_state: st.session_state.current_grid_state = pd.DataFrame()
# ➡️ AÑADE ESTA LÍNEA JUSTO AQUÍ ABAJO:
if 'reload_trigger' not in st.session_state: st.session_state.reload_trigger = False

df = st.session_state.df

partidas_unicas_global = df['Partida'].unique() if not df.empty else []
paleta_colores_global = px.colors.qualitative.Alphabet + px.colors.qualitative.Light24 + px.colors.qualitative.Dark24
mapa_colores_partida = {partida: paleta_colores_global[i % len(paleta_colores_global)] for i, partida in enumerate(partidas_unicas_global)}

if 'lote_actual' not in st.session_state: st.session_state.lote_actual = str(df['Lote'].unique()[0]) if not df.empty else "1"
if 'mostrar_todos_mapa' not in st.session_state: st.session_state.mostrar_todos_mapa = False

if 'sel_proto' not in st.session_state: st.session_state.sel_proto = "Todos"
if 'sel_manzana' not in st.session_state: st.session_state.sel_manzana = "Todos"
if 'sel_lotes' not in st.session_state: st.session_state.sel_lotes = []
if 'sel_concepto' not in st.session_state: st.session_state.sel_concepto = []
if 'sel_dest' not in st.session_state: st.session_state.sel_dest = "Todos"
if 'sel_estado' not in st.session_state: st.session_state.sel_estado = "Todos"
if 'sel_fecha' not in st.session_state: st.session_state.sel_fecha = ()

# --- 1. FORMULARIO DE ACCESO ---
def login():
    mostrar_cabecera_con_logo("🔐 Control de estimaciones", "Por favor, introduce tus credenciales para ingresar.")
    
    # Creamos 3 columnas: las de los extremos ([1.2] y [1.2]) sirven como espacio en blanco 
    # para empujar y centrar la columna del medio ([1]), dándole un tamaño estético y proporcional.
    col_izq, col_centro, col_der = st.columns([1.2, 1, 1.2])
    
    with col_centro:
        st.markdown("<br>", unsafe_allow_html=True) # Pequeño espacio para que no quede pegado a la cabecera
        
        usuario = st.text_input("Usuario", key="input_user")
        contrasena = st.text_input("Contraseña", type="password", key="input_pass")
        
        # Agregamos use_container_width=True para que el botón abarque exactamente el mismo ancho de las celdas
        if st.button("Ingresar", use_container_width=True, type="primary"):
            usuarios_validos = st.secrets["usuarios"] if "usuarios" in st.secrets else {}
            if usuario in usuarios_validos and usuarios_validos[usuario] == contrasena:
                st.session_state.usuario = usuario
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos")

if st.session_state.usuario is None:
    login()
    st.stop()

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

# --- BOTONES DE LA BARRA LATERAL ---
if st.sidebar.button("💾 GUARDAR CAMBIOS"):
    df_actual_pantalla = st.session_state.current_grid_state
    
    if df_actual_pantalla.empty:
        st.sidebar.warning("No hay cambios en pantalla para guardar.")
    else:
        # Forzar booleanos limpios por seguridad de evaluación
        df_actual_pantalla['Pagar_Bool'] = df_actual_pantalla['Pagar'].astype(str).str.lower().isin(['true', '1'])
        
        # CORRECCIÓN: Limpieza absoluta para detectar de forma segura las celdas vacías devueltas por AgGrid (evita fallos por None o NaN)
        df_actual_pantalla['Fecha_Pago_Limpia'] = df_actual_pantalla['Fecha pago'].fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>'], '')
        
        filas_a_pagar = df_actual_pantalla[(df_actual_pantalla['Pagar_Bool'] == True) & (df_actual_pantalla['Fecha_Pago_Limpia'] == '')]
        filas_invalidas = filas_a_pagar[(filas_a_pagar['Destajista'].astype(str).str.strip() == '') | (filas_a_pagar['C.C'].astype(str).str.strip() == '')]
        
        if not filas_invalidas.empty:
            st.sidebar.error("❌ ¡ALTO! Hay partidas marcadas para pagar sin 'Destajista' o 'C.C' asignado. Completa los datos antes de guardar.")
        else:
            with st.spinner("Sincronizando con Google..."):
                dt_actual = datetime.now(ZoneInfo("America/Mexico_City"))
                meses_esp = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                ahora = f"{dt_actual.day:02d}/{meses_esp[dt_actual.month]}/{dt_actual.year} {dt_actual.strftime('%H:%M:%S')}"
                usuario_actual = st.session_state.usuario
                
                # 1. Guardar partidas que se van a pagar
                if not filas_a_pagar.empty:
                    for _, row in filas_a_pagar.iterrows():
                        idx_original = int(row['_original_index'])
                        st.session_state.df.at[idx_original, 'Destajista'] = str(row['Destajista']).strip()
                        st.session_state.df.at[idx_original, 'C.C'] = str(row['C.C']).strip()
                        st.session_state.df.at[idx_original, 'Pagar'] = True
                        st.session_state.df.at[idx_original, 'Fecha pago'] = ahora
                        st.session_state.df.at[idx_original, 'Usuario'] = usuario_actual
                
                # 2. Guardar partidas que solo se editaron (Destajista o CC) sin pagar aún
                filas_solo_edicion = df_actual_pantalla[(df_actual_pantalla['Pagar_Bool'] == False) & (df_actual_pantalla['Fecha_Pago_Limpia'] == '')]
                for _, row in filas_solo_edicion.iterrows():
                    idx_original = int(row['_original_index'])
                    st.session_state.df.at[idx_original, 'Destajista'] = str(row['Destajista']).strip() if pd.notna(row['Destajista']) else ""
                    st.session_state.df.at[idx_original, 'C.C'] = str(row['C.C']).strip() if pd.notna(row['C.C']) else ""

                # 3. Eliminar columnas temporales "fantasmas" antes de enviar a la API
                df_envio = st.session_state.df.copy()
                if 'Concepto_Limpio' in df_envio.columns:
                    df_envio = df_envio.drop(columns=['Concepto_Limpio'])

                actualizar_datos_gsheet(df_envio)
                
                # 4. Sincronizar memoria y forzar refresco limpio de pantalla
                st.session_state.df_original = st.session_state.df.copy()
                st.session_state.current_grid_state = pd.DataFrame() 
                st.session_state.grid_key += 1 
                st.success("¡Datos guardados!")
                st.rerun()

# (Corrección 4) Rango de fechas unificado para evitar cierre del modal
@st.dialog("🖨️ Generar Reporte de Pagos", width="large")
def dialogo_reportes():
    st.markdown("### Selecciona el rango de fechas para el reporte")
    st.info("Selecciona la fecha de inicio y luego la fecha final en el mismo calendario.")
    rango = st.date_input("Rango de fechas", value=[], format="DD/MM/YYYY")
    
    if len(rango) == 2:
        f_inicio, f_fin = rango[0], rango[1]
        if st.button("Imprimir PDF", type="primary"):
            df_rep = st.session_state.df[st.session_state.df['Fecha pago'] != ''].copy()
            df_rep['Fecha_Obj'] = pd.to_datetime(df_rep['Fecha pago'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date
            df_rep = df_rep[(df_rep['Fecha_Obj'] >= f_inicio) & (df_rep['Fecha_Obj'] <= f_fin)]
            
            if df_rep.empty:
                st.warning("No hay pagos registrados en este rango de fechas.")
            else:
                df_agrupado = df_rep.groupby(['Destajista', 'C.C'])['Costo'].sum().reset_index()
                
                pdf = FPDF(orientation='P', unit='mm', format='Letter')
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(200, 10, txt=f"Reporte de Pagos", ln=True, align='C')
                pdf.set_font("Arial", '', 12)
                pdf.cell(200, 10, txt=f"Del: {f_inicio.strftime('%d/%m/%Y')} Al: {f_fin.strftime('%d/%m/%Y')}", ln=True, align='C')
                pdf.ln(10)
                
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(80, 10, txt="Destajista", border=1)
                pdf.cell(70, 10, txt="Centro de Costo (C.C)", border=1)
                pdf.cell(40, 10, txt="Cantidad Pagada", border=1, ln=True, align='R')
                
                pdf.set_font("Arial", '', 10)
                total_global = 0
                for _, r in df_agrupado.iterrows():
                    pdf.cell(80, 10, txt=str(r['Destajista'])[:35], border=1)
                    pdf.cell(70, 10, txt=str(r['C.C'])[:30], border=1)
                    pdf.cell(40, 10, txt=f"${float(r['Costo']):,.2f}", border=1, ln=True, align='R')
                    total_global += float(r['Costo'])
                
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(150, 10, txt="TOTAL", border=1, align='R')
                pdf.cell(40, 10, txt=f"${total_global:,.2f}", border=1, ln=True, align='R')
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    pdf.output(tmp_file.name)
                    with open(tmp_file.name, "rb") as f:
                        st.download_button("📥 Descargar Reporte PDF", data=f, file_name=f"Reporte_Pagos_{f_inicio}_{f_fin}.pdf", mime="application/pdf")

if st.sidebar.button("📄 Reportes"):
    dialogo_reportes()

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state.usuario = None
    st.rerun()

# --- TABLA DE RESUMEN DE PROTOTIPOS EN EL PANEL LATERAL (INFERIOR) ---
if not st.session_state.df.empty:
    df_side = st.session_state.df.copy()
    df_side['Costo'] = pd.to_numeric(df_side['Costo'], errors='coerce').fillna(0)
    
    # Agrupar por prototipo: Contar casas (Lotes únicos) y sumar Costo
    df_resumen_proto = df_side.groupby('Prototipo').agg(
        Cantidad=('Lote', 'nunique'),
        Costo=('Costo', 'sum')
    ).reset_index()
    
    # Aplicar ordenamiento natural nativo (1, 1+, 2, 2+, 2A...)
    df_resumen_proto['sort_key'] = df_resumen_proto['Prototipo'].apply(natural_sort_key)
    df_resumen_proto = df_resumen_proto.sort_values(by='sort_key').drop(columns=['sort_key'])
    
    total_cantidad_protos = df_resumen_proto['Cantidad'].sum()
    total_general_protos = df_resumen_proto['Costo'].sum()
    
    # Dar formato estético
    df_mostrar_sidebar = df_resumen_proto.copy()
    df_mostrar_sidebar['Total'] = df_mostrar_sidebar['Costo'].apply(lambda x: f"${x:,.2f}")
    df_mostrar_sidebar = df_mostrar_sidebar[['Prototipo', 'Cantidad', 'Total']]
    
    # Añadir renglón final con sumatorias totales
    fila_total = pd.DataFrame([{
        'Prototipo': 'TOTAL', 
        'Cantidad': total_cantidad_protos, 
        'Total': f"${total_general_protos:,.2f}"
    }])
    df_mostrar_sidebar = pd.concat([df_mostrar_sidebar, fila_total], ignore_index=True)
    
    # Dibujar la tabla limpia en el panel de la izquierda
    st.sidebar.markdown("<br><hr>", unsafe_allow_html=True)
    st.sidebar.markdown("##### 📊 Resumen por Prototipo")
    st.sidebar.dataframe(df_mostrar_sidebar, hide_index=True, use_container_width=True)

# =========================================================================
# PESTAÑA 1: REGISTRO DE DESTAJOS
# =========================================================================
if menu == "Registro de Destajos":
    mostrar_cabecera_con_logo("📝 Control de Pagos Destajos")
    
    df_actual = st.session_state.df
    
    st.markdown("##### ⏳ Filtros de Tabla")
    
    def limpiar_cb():
        st.session_state.sel_proto = "Todos"
        st.session_state.sel_manzana = "Todos"
        st.session_state.sel_lotes = []
        st.session_state.sel_concepto = []
        st.session_state.sel_dest = "Todos"
        st.session_state.sel_estado = "Todos"
        st.session_state.sel_fecha = ()
        st.session_state.grid_key += 1 
        
    st.button("🧹 Limpiar todos los filtros", on_click=limpiar_cb)

    list_prototipos = sorted(df_actual['Prototipo'].unique().tolist(), key=natural_sort_key)
    list_manzanas = sorted([x for x in df_actual['Manzana'].unique().tolist() if str(x).strip()], key=natural_sort_key)
    list_lotes = sorted([str(x) for x in df_actual['Lote'].unique().tolist() if str(x).strip()], key=natural_sort_key)
    list_destajistas_filtro = ["Todos"] + [d for d in LISTA_DESTAJISTAS if d != ""]
    
    df_temporal_filtros = df_actual.copy()
    df_temporal_filtros['Concepto_Limpio'] = df_temporal_filtros['Partida'].apply(lambda x: re.sub(r'^\d+\.-s*|^\d+\s*', '', str(x)).strip())
    
    conceptos_unicos_tuplas = {}
    for _, row in df_temporal_filtros.iterrows():
        limpio = row['Concepto_Limpio']
        if limpio not in conceptos_unicos_tuplas:
            conceptos_unicos_tuplas[limpio] = sort_conceptos(row['Partida'])
    list_conceptos = sorted(conceptos_unicos_tuplas.keys(), key=lambda k: conceptos_unicos_tuplas[k])

    f_col1, f_col2 = st.columns(2)
    
    with f_col1:
        st.selectbox("Prototipo:", ["Todos"] + list_prototipos, key="sel_proto")
        st.multiselect("Lote(s):", options=list_lotes, key="sel_lotes")
        st.multiselect("Concepto / Partida:", options=list_conceptos, key="sel_concepto")
        
    with f_col2:
        st.selectbox("Manzana:", ["Todos"] + list_manzanas, key="sel_manzana")
        st.selectbox("Estado de Pago:", ["Todos", "Pendiente", "Pagado"], key="sel_estado")
        st.selectbox("Destajista:", list_destajistas_filtro, key="sel_dest")
        st.date_input("Fecha de Pago (Rango):", format="DD/MM/YYYY", key="sel_fecha")

    # --- APLICAR FILTROS ---
    df_filtrado = df_actual.copy()
    df_filtrado['Concepto_Limpio'] = df_filtrado['Partida'].apply(lambda x: re.sub(r'^\d+\.-s*|^\d+\s*', '', str(x)).strip())
    if st.session_state.sel_proto != "Todos": df_filtrado = df_filtrado[df_filtrado['Prototipo'] == st.session_state.sel_proto]
    if st.session_state.sel_manzana != "Todos": df_filtrado = df_filtrado[df_filtrado['Manzana'] == st.session_state.sel_manzana]
    if st.session_state.sel_lotes: df_filtrado = df_filtrado[df_filtrado['Lote'].astype(str).isin(st.session_state.sel_lotes)]
    if st.session_state.sel_concepto: df_filtrado = df_filtrado[df_filtrado['Concepto_Limpio'].isin(st.session_state.sel_concepto)]
    if st.session_state.sel_dest != "Todos": df_filtrado = df_filtrado[df_filtrado['Destajista'] == st.session_state.sel_dest]
    
    if st.session_state.sel_estado != "Todos":
        if st.session_state.sel_estado == "Pagado": df_filtrado = df_filtrado[df_filtrado['Fecha pago'] != '']
        else: df_filtrado = df_filtrado[df_filtrado['Fecha pago'] == '']
            
    if st.session_state.sel_fecha and len(st.session_state.sel_fecha) == 2:
        df_filtrado['Fecha_Obj_Temp'] = pd.to_datetime(df_filtrado['Fecha pago'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date
        df_filtrado = df_filtrado[(df_filtrado['Fecha_Obj_Temp'] >= st.session_state.sel_fecha[0]) & (df_filtrado['Fecha_Obj_Temp'] <= st.session_state.sel_fecha[1])]
        df_filtrado = df_filtrado.drop(columns=['Fecha_Obj_Temp'])

    # --- CÁLCULO DE KPI REACTIVOS (Usando la tabla ya filtrada) ---
    costo_total_filtrado = df_filtrado['Costo'].sum()
    pagado_filtrado = df_filtrado.loc[df_filtrado['Fecha pago'] != '', 'Costo'].sum()
    pendiente_filtrado = costo_total_filtrado - pagado_filtrado
    
    st.markdown(f"""
    <div style="background-color:{COLOR_FONDO_PROTOTIPO}; padding:20px; border-radius:10px; margin-bottom:20px; color:{COLOR_TEXTO_PROTOTIPO};">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.3); padding-bottom: 10px;">
            <div style="font-size:24px; font-weight:bold;">🏠 Resumen de la Selección</div>
        </div>
        <div style="display: flex; justify-content: space-between; gap: 15px; flex-wrap: wrap;">
            <div style="flex: 1; text-align: center; background-color:rgba(255,255,255,0.1); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Costo Total Filtrado</div>
                <div style="font-size:24px; font-weight:bold;">${costo_total_filtrado:,.2f}</div>
            </div>
            <div style="flex: 1; text-align: center; background-color:rgba(16, 185, 129, 0.4); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Total Pagado Real</div>
                <div style="font-size:24px; font-weight:bold;">${pagado_filtrado:,.2f}</div>
            </div>
            <div style="flex: 1; text-align: center; background-color:rgba(239, 68, 68, 0.5); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Total por Pagar</div>
                <div style="font-size:24px; font-weight:bold;">${pendiente_filtrado:,.2f}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns([1.5, 1.5, 2, 2, 2])
    
    if b_col1.button("☑️ Seleccionar Todos", use_container_width=True):
        st.session_state.df.loc[df_filtrado.index, 'Pagar'] = True
        st.session_state.grid_key += 1
        st.rerun()
        
    if b_col2.button("🔲 Seleccionar Ninguno", use_container_width=True):
        # 1. Filtramos para obtener solo los índices de las partidas que NO tienen fecha de pago
        indices_pendientes = df_filtrado[df_filtrado['Fecha pago'] == ''].index
        # 2. Desmarcamos solo esas partidas pendientes, respetando las bloqueadas
        st.session_state.df.loc[indices_pendientes, 'Pagar'] = False
        st.session_state.grid_key += 1
        st.rerun()

    destajista_masivo = b_col3.selectbox("Destajista M.", ["Seleccionar..."] + LISTA_DESTAJISTAS, label_visibility="collapsed")
    if b_col3.button("Asignar Destajista Masivo", use_container_width=True):
        if destajista_masivo != "Seleccionar...":
            st.session_state.df.loc[df_filtrado.index, 'Destajista'] = destajista_masivo
            st.session_state.grid_key += 1
            st.success("Destajista asignado masivamente.")
            st.rerun()

    cc_masivo = b_col4.selectbox("C.C M.", ["Seleccionar..."] + LISTA_CC, label_visibility="collapsed")
    if b_col4.button("Asignar C.C Masivo", use_container_width=True):
        if cc_masivo != "Seleccionar...":
            st.session_state.df.loc[df_filtrado.index, 'C.C'] = cc_masivo
            st.session_state.grid_key += 1
            st.success("C.C asignado masivamente.")
            st.rerun()

    # --- INICIO NUEVO BOTÓN DE SELLADO ---
    col_sellar, col_espacio = st.columns([2, 8])
    if col_sellar.button("✍️ Sellar Fecha y Usuario", use_container_width=True, type="primary"):
        df_pantalla = st.session_state.current_grid_state
        if not df_pantalla.empty:
            df_pantalla['Pagar_Bool'] = df_pantalla['Pagar'].astype(str).str.lower().isin(['true', '1'])
            df_pantalla['Fecha_Limpia'] = df_pantalla['Fecha pago'].fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>'], '')
            filas_sellar = df_pantalla[(df_pantalla['Pagar_Bool'] == True) & (df_pantalla['Fecha_Limpia'] == '')]
            
            if not filas_sellar.empty:
                # --- LÓGICA DE HORA EXACTA Y FORMATO EN ESPAÑOL ---
                dt_actual = datetime.now(ZoneInfo("America/Mexico_City"))
                meses_esp = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                ahora = f"{dt_actual.day:02d}/{meses_esp[dt_actual.month]}/{dt_actual.year} {dt_actual.strftime('%H:%M:%S')}"
                # --------------------------------------------------
                for _, row in filas_sellar.iterrows():
                    idx = int(row['_original_index'])
                    st.session_state.df.at[idx, 'Fecha pago'] = ahora
                    st.session_state.df.at[idx, 'Usuario'] = st.session_state.usuario
                    st.session_state.df.at[idx, 'Destajista'] = str(row['Destajista']).strip() if pd.notna(row['Destajista']) else ""
                    st.session_state.df.at[idx, 'C.C'] = str(row['C.C']).strip() if pd.notna(row['C.C']) else ""
                    st.session_state.df.at[idx, 'Pagar'] = True
                
                st.session_state.grid_key += 1
                st.session_state.reload_trigger = True
                st.rerun()
            else:
                st.warning("Selecciona primero la casilla 'Pagar' en las partidas que desees sellar.")
    # --- FIN NUEVO BOTÓN DE SELLADO ---

    ph_label_azul = st.empty()
    st.markdown("<hr style='margin:5px 0 5px 0;'>", unsafe_allow_html=True)
    
    df_filtrado_grid = df_filtrado.copy()
    df_filtrado_grid['_original_index'] = df_filtrado_grid.index
    
    gb = GridOptionsBuilder.from_dataframe(df_filtrado_grid[['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', 'C.C', 'Pagar', 'Fecha pago', 'Usuario', '_original_index']])
    
    gb.configure_default_column(sortable=False, filter=False, resizable=True)
    gb.configure_column("_original_index", hide=True)
    
    gb.configure_column("Lote", editable=False, filter=False, cellStyle={'textAlign': 'center'}, width=90)
    gb.configure_column("Manzana", editable=False, cellStyle={'textAlign': 'center'}, width=100)
    gb.configure_column("Prototipo", editable=False, cellStyle={'textAlign': 'center'}, width=110)
    gb.configure_column("Partida", editable=False, width=300) 
    gb.configure_column("Costo", editable=False, filter=False, valueFormatter="x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})", cellStyle={'textAlign': 'right'}, width=120)
    
    gb.configure_column("Destajista", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': LISTA_DESTAJISTAS}, width=200)
    gb.configure_column("C.C", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': LISTA_CC}, cellStyle={'textAlign': 'center'}, width=180)
    
    gb.configure_column("Pagar", editable=True, cellStyle={'textAlign': 'center'}, width=90)
    gb.configure_column("Fecha pago", editable=False, cellStyle={'textAlign': 'center'}, width=160)
    gb.configure_column("Usuario", editable=False, cellStyle={'textAlign': 'center'}, width=120)

    # (Corrección 1) Comprobación segura en el front-end para saber si está pagado o no (sin evaluar basura de texto)
    rowStyle = JsCode("""
    function(params) {
        let fp = params.data['Fecha pago'];
        let esta_pagado = (fp && fp.toString().trim() !== '' && fp !== 'nan' && fp !== 'null' && fp !== '<NA>');
        
        if (esta_pagado) {
            return {
                'backgroundColor': '#e0e0e0',
                'color': '#808080',
                'pointerEvents': 'none',
                'borderBottom': '1px solid #d3d3d3'
            };
        }
        
        let style = {
            'backgroundColor': '#000000',
            'color': '#39FF14',
            'borderBottom': '1px solid #4a4a4a'
        };
        
        let check_pagar = params.data['Pagar'];
        if (check_pagar === true || check_pagar === 'true' || check_pagar === 1) {
            let dest = params.data['Destajista'];
            let cc = params.data['C.C'];
            if (!dest || dest.trim() === '' || !cc || cc.trim() === '') {
                style['backgroundColor'] = '#4a0000';
            }
        }
        return style;
    }
    """)
    gb.configure_grid_options(getRowStyle=rowStyle, rowHeight=35)
    
    grid_options = gb.build()

    # (Corrección 3) reload_data=False evita que la tabla parpadee y pierda el foco al escribir.
    response = AgGrid(
        df_filtrado_grid[['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', 'C.C', 'Pagar', 'Fecha pago', 'Usuario', '_original_index']],
        gridOptions=grid_options,
        key=f"grid_destajos_{st.session_state.grid_key}",
        reload_data=st.session_state.reload_trigger,
        enable_enterprise_modules=False,
        allow_unsafe_jscode=True,
        update_mode=GridUpdateMode.MANUAL,
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        theme='balham',
        height=600
    )
    st.session_state.reload_trigger = False

    if response['data'] is not None and not pd.DataFrame(response['data']).empty:
        df_grid = pd.DataFrame(response['data'])
        st.session_state.current_grid_state = df_grid 
        
        total_filas = len(df_grid)
        df_grid['Pagar_Bool'] = df_grid['Pagar'].astype(str).str.lower().isin(['true', '1'])
        df_pagar = df_grid[df_grid['Pagar_Bool'] == True]
        total_checked = len(df_pagar)
        
        costo_seleccionado = df_pagar[df_pagar['Fecha pago'] == '']['Costo'].sum()
        
        ph_label_azul.markdown(f"<div style='color: #3B82F6; font-weight: bold; background: transparent; font-size:14px; margin-bottom:5px;'>Partidas en pantalla: {total_filas} / Checkbox activados: {total_checked}</div>", unsafe_allow_html=True)
        b_col5.markdown(f"<div style='background-color:#F59E0B; color:black; padding:10px; border-radius:5px; text-align:center; font-weight:bold; font-size:18px;'>Suma a Pagar:<br>${costo_seleccionado:,.2f}</div>", unsafe_allow_html=True)
    else:
        ph_label_azul.markdown("<div style='color: #3B82F6; font-weight: bold; background: transparent; font-size:14px; margin-bottom:5px;'>Partidas en pantalla: 0 / Checkbox activados: 0</div>", unsafe_allow_html=True)
        b_col5.markdown(f"<div style='background-color:#F59E0B; color:black; padding:10px; border-radius:5px; text-align:center; font-weight:bold; font-size:18px;'>Suma a Pagar:<br>$0.00</div>", unsafe_allow_html=True)


# =========================================================================
# PESTAÑA 2: DASHBOARD INTERACTIVO Y GERENCIAL 
# =========================================================================
elif menu == "Dashboard (Gráficos y Visor)":
    mostrar_cabecera_con_logo("📊 Visor Estadístico e Indicadores")
    
    df_dash_base = df.copy()
    df_dash_base['Precio'] = df_dash_base['Costo']
    df_dash_base['Total_Pagado_Real'] = df_dash_base.apply(lambda r: r['Costo'] if r['Fecha pago'] != '' else 0, axis=1)
    df_dash_base['Estado'] = df_dash_base.apply(lambda r: 'Pagado' if r['Fecha pago'] != '' else 'Pendiente', axis=1)

    def ordenar_prototipos(val):
        match = re.search(r"(\d+)(.*)", str(val))
        if match:
            return (int(match.group(1)), match.group(2))
        return (float('inf'), str(val))

    st.markdown("### 🔍 Panel de Control y Filtros Dinámicos")
    
    d_col1, d_col2, d_col3 = st.columns(3)
    protos_disponibles = sorted(df_dash_base['Prototipo'].unique(), key=ordenar_prototipos)
    lotes_disponibles = sorted(list(df_dash_base['Lote'].unique()), key=natural_sort_key)
    destajistas_disponibles = ["Todos"] + sorted(list(df_dash_base['Destajista'].replace('', pd.NA).dropna().unique()), key=natural_sort_key)
    
    if 'tab2_lotes_seleccionados' not in st.session_state:
        st.session_state.tab2_lotes_seleccionados = lotes_disponibles
        
    protos_dash = d_col1.multiselect("Filtrar por Prototipos:", options=protos_disponibles, default=protos_disponibles)
    lotes_dash = d_col2.multiselect("Filtrar por Lotes:", options=lotes_disponibles, key="tab2_lotes_seleccionados")
    destajista_dash = d_col3.selectbox("Filtrar por Destajista Global:", options=destajistas_disponibles)
    
    df_dash = df_dash_base[(df_dash_base['Lote'].isin(lotes_dash)) & (df_dash_base['Prototipo'].isin(protos_dash))].copy()
    if destajista_dash != "Todos":
        df_dash = df_dash[df_dash['Destajista'] == destajista_dash]
    
    if df_dash.empty:
        st.warning("⚠️ No hay datos para mostrar con los filtros seleccionados.")
    else:
        monto_total = df_dash['Precio'].sum()
        monto_pagado = df_dash['Total_Pagado_Real'].sum()
        monto_pendiente = monto_total - monto_pagado
        
        df_pagados = df_dash[df_dash['Estado'] == 'Pagado'] 
        
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
                               color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#EF4444'})
            fig_proto.update_traces(textposition='outside')
            g_col1.plotly_chart(fig_proto, use_container_width=True)
            
            fig_tree = px.treemap(df_dash, path=[px.Constant("Proyecto EGC"), 'Prototipo', 'Lote', 'Estado'], values='Precio',
                                  title="Distribución del Presupuesto (Clic para explorar)",
                                  color='Estado', color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#EF4444', '(?)': '#cbd5e1'})
            fig_tree.update_traces(root_color="lightgrey")
            fig_tree.update_layout(margin=dict(t=50, l=25, r=25, b=25))
            g_col2.plotly_chart(fig_tree, use_container_width=True)
            
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
                df_deudores_clean = df_deudores.replace('', 'Sin Asignar').fillna("Sin Asignar")
                df_deuda = df_deudores_clean.groupby('Destajista')['Deuda'].sum().reset_index().sort_values('Deuda', ascending=True)
                fig_deuda = px.bar(df_deuda, y='Destajista', x='Deuda', orientation='h',
                                   title="🚨 Pagos Pendientes por Destajista (Deuda Restante)",
                                   color_discrete_sequence=['#EF4444'], text_auto='$.2s')
                g_col4.plotly_chart(fig_deuda, use_container_width=True)
            else:
                g_col4.success("¡Excelente! No hay deuda pendiente para la selección actual.")


# =========================================================================
# PESTAÑA 3: MAPA INTERACTIVO (VERSIÓN UNIFICADA A 'COSTO' Y PARSER SEGURO)
# =========================================================================
# =========================================================================
# PESTAÑA 3: MAPA INTERACTIVO (RESTAURADA VERSIÓN ANTERIOR Y ADAPTADA A 'COSTO')
# =========================================================================
elif menu == "Mapa Interactivo":
    mostrar_cabecera_con_logo("🗺️ Plano Interactivo Dinámico", "Visualización gráfica del avance del desarrollo.")

    # --- ADAPTACIÓN AL NUEVO MODELO DE DATOS ---
    df_map_base = df.copy()
    df_map_base['Costo'] = pd.to_numeric(df_map_base['Costo'], errors='coerce').fillna(0)
    # Lógica actual: Si tiene fecha de pago, está 100% Pagado. Si no, está Pendiente.
    df_map_base['Estado'] = df_map_base.apply(lambda r: 'Pagado' if str(r['Fecha pago']).strip() != '' else 'Pendiente', axis=1)

    def hex_to_rgba(hex_val, opacity):
        hex_val = hex_val.lstrip('#')
        if len(hex_val) == 6:
            return f"rgba({int(hex_val[0:2], 16)}, {int(hex_val[2:4], 16)}, {int(hex_val[4:6], 16)}, {opacity})"
        return "rgba(0,0,0,0)"

    # --- ARCHIVO DE COORDENADAS INTERNO ORIGINAL ---
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
        df_lote_mapa = df_map_base[df_map_base['Lote'].astype(str).str.strip() == str(lote_num)].copy()
        
        if not df_lote_mapa.empty:
            total_partidas = len(df_lote_mapa)
            # Adaptación para calcular lo que está realmente pagado sumando el Costo de las partidas terminadas
            df_lote_mapa['Total_Pagado_Real'] = df_lote_mapa.apply(lambda r: r['Costo'] if r['Estado'] == 'Pagado' else 0, axis=1)
            total_precio_lote = df_lote_mapa['Costo'].sum()
            total_pagado_lote = df_lote_mapa['Total_Pagado_Real'].sum()
            
            porcentaje = (total_pagado_lote / total_precio_lote * 100) if total_precio_lote > 0 else 0
            pagadas_completas = len(df_lote_mapa[df_lote_mapa['Estado'] == 'Pagado'])
            
            # --- LÓGICA ORIGINAL DE ETAPAS DE OBRA ---
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
        df_kpi = df_map_base.copy()
        titulo_kpi = "🏠 Proyecto General (Todos los Lotes)"
    else:
        lote_puro_kpi = str(st.session_state.lote_actual)
        df_kpi = df_map_base[df_map_base['Lote'].astype(str).str.strip() == lote_puro_kpi].copy()
        
        prototipo_kpi = df_kpi['Prototipo'].iloc[0] if not df_kpi.empty else "N/A"
        titulo_kpi = f"🏠 Lote {lote_puro_kpi} - Prototipo {prototipo_kpi}"
        
    df_kpi['Total_Pagado_Real'] = df_kpi.apply(lambda r: r['Costo'] if r['Estado'] == 'Pagado' else 0, axis=1)
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
    for p in df_map_base['Partida'].dropna().unique():
        if str(p).strip() and str(p) not in partidas_ordenadas:
            partidas_ordenadas.append(str(p))
            
    partidas_display = [f"{i}.- {p}" for i, p in enumerate(partidas_ordenadas, start=1)]
    destajistas_unicos_filtro = sorted([str(d) for d in df_map_base['Destajista'].dropna().unique() if str(d).strip()], key=natural_sort_key)
    
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
    
    # Adaptado a solo buscar los que ya fueron Pagados para los filtros interactivos
    df_filtered = df_map_base[df_map_base['Estado'] == 'Pagado'].copy()
    if filtro_partidas_mapa:
        df_filtered = df_filtered[df_filtered['Partida'].isin(filtro_partidas_mapa)]
    if filtro_destajistas_mapa:
        df_filtered = df_filtered[df_filtered['Destajista'].isin(filtro_destajistas_mapa)]

    # --- LEYENDA VISUAL DE AVANCES ORIGINAL ---
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

        # --- LÓGICA DE LA TABLA (SEPARACIÓN MOSTRAR TODOS vs LOTE ESPECÍFICO) ---
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
                df_resumen_global = df_map_base.copy()
                df_resumen_global['Total_Pagado_Real'] = df_resumen_global.apply(lambda r: r['Costo'] if r['Estado'] == 'Pagado' else 0, axis=1)
                
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
            # MOSTRANDO LOTE ESPECÍFICO (Cruzando datos con filtros activos)
            lote_puro_num = str(st.session_state.lote_actual)
            
            if filtros_activos:
                st.markdown(f"**Desglose Filtrado (Lote {lote_puro_num}):**")
                df_desglose_lote = df_filtered[df_filtered['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Costo']].copy()
            else:
                st.markdown(f"**Desglose General (Lote {lote_puro_num}):**")
                df_desglose_lote = df_map_base[df_map_base['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Costo']].copy()
            
            if not df_desglose_lote.empty:
                def formatear_estado_icono(val):
                    if val == "Pagado": return "🟢 100% PAGADO"
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
                    "<th style='padding: 10px; border-bottom: 2px solid #ddd;'>Costo</th>"
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
                        f"<td style='padding: 8px;'>${row_lote['Costo']:,.2f}</td>"
                        "</tr>"
                    )
                html_table += "</tbody></table></div>"
                st.markdown(html_table, unsafe_allow_html=True)
            else:
                msg = f"No hay partidas que coincidan con tus filtros en el lote {lote_puro_num}." if filtros_activos else f"No se encontraron partidas para el lote {lote_puro_num}."
                st.info(msg)

    with col_mapa:
        # --- AQUÍ EMPIEZA LA INTEGRACIÓN DEL SVG PURO CON ESFERAS Y RELLENOS (VERSIÓN ANTERIOR) ---
        nombres_posibles = ["SVGsembrado.txt"]
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
                        # --- MEJORA DE LEYENDA HOVER EN EL POLÍGONO ---
                        etiqueta_hover = lote_path.find('title')
                        if not etiqueta_hover:
                            etiqueta_hover = soup.new_tag('title')
                            lote_path.append(etiqueta_hover)
                        
                        # Extraemos el porcentaje y la fase (Estado) directamente de los datos del lote
                        avance_lote = item["Avance"]
                        fase_lote = item["Estado"]
                        
                        # Formateamos la leyenda limpia: Lote X | Avance: XX% | Fase
                        etiqueta_hover.string = f"Lote {id_lote} | Avance: {avance_lote} | {fase_lote}"

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

                                        # --- LÓGICA DE CORTE RECTANGULAR AUTOCONTENIDA ORIGINAL ---
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
                                    df_lote_esferas = df_map_base[df_map_base['Lote'].astype(str).str.strip() == id_lote]

                        
                html_final = str(soup).replace("viewbox=", "viewBox=")
                html_final = f"<div style='width:100%; height:1000px; display:flex; justify-content:center; align-items: center;'>{html_final}</div>"
                st.components.v1.html(html_final, height=1000, scrolling=False) 

            except Exception as e:
                st.error("⚠️ Hubo un problema al procesar el archivo SVG.")
                st.write(f"Detalle del error técnico: {e}")
        else:
            st.error("⚠️ No se encontró el archivo del mapa.")
            st.info(f"Por favor asegúrate de tener el archivo de texto en la misma carpeta que app.py y que se llame de alguna de estas formas: {nombres_posibles}")
        # --- FIN DE LA INTEGRACIÓN DEL SVG ---

    # --- INICIO DEL DIAGRAMA INTERACTIVO INYECTADO DEBAJO DEL MAPA (VERSIÓN ANTERIOR ADAPTADA) ---
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("### 🔗 Diagrama Interactivo de Partidas")
    
    if st.session_state.mostrar_todos_mapa:
        st.info("⚠️ Selecciona un Lote específico desde el panel 'Desglose' (arriba a la derecha) para visualizar este diagrama.")
    else:
        df_lote_diag = df_map_base[df_map_base['Lote'].astype(str).str.strip() == str(st.session_state.lote_actual)]

        if not df_lote_diag.empty:
            num_partidas = len(df_lote_diag)
            cols = math.ceil(math.sqrt(num_partidas))

            filas = math.ceil(num_partidas / cols) if cols > 0 else 1
            
            x_coords, y_coords, colores_relleno, textos_hover = [], [], [], []

            # 1. Cuadrícula virtual perfecta original (10x5)
            ancho_celda = 10
            alto_celda = 5
            
            for i, row in enumerate(df_lote_diag.itertuples()):
                col_actual = i % cols
                fila_actual = i // cols
                
                # 2. Posicionamiento en intersecciones
                x = (col_actual * ancho_celda) + (ancho_celda / 2.0)
                y = (fila_actual * alto_celda) + (alto_celda / 2.0)
                    
                x_coords.append(x)
                y_coords.append(y)

                estado = row.Estado
                costo = row.Costo # ADAPTADO A LA COLUMNA ACTUAL
                pago_real = costo if estado == 'Pagado' else 0.0 # ADAPTADO
                destajista = row.Destajista if pd.notna(row.Destajista) and row.Destajista != "" else "Sin Asignar"
                
                color_asignado = mapa_colores_partida.get(row.Partida, "#3B82F6")

                # RELLENOS EXACTOS DE VERSIÓN ANTERIOR
                if estado == "Pagado":
                    colores_relleno.append(color_asignado)
                else:
                    colores_relleno.append("rgba(0,0,0,0)") # Sin relleno si no está pagado

                hover_text = f"<b>Partida:</b> {row.Partida}<br><b>Costo Total:</b> ${costo:,.2f}<br><b>Pagado:</b> ${pago_real:,.2f}<br><b>Destajista:</b> {destajista}<br><b>Estado:</b> {estado}"
                textos_hover.append(hover_text)

            # 3. Altura física y diseño visual estricto de la versión anterior
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
                    line=dict(width=1, color="#374151") # Bordes mínimos para las esferas transparentes 
                ),
                text=textos_hover,
                hoverinfo='text'
            ))

            # 4. Rectángulo verde brillante para delimitar
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

            # 5. Geometría fijada en 1:1 para evitar deformaciones
            fig_diag.update_layout(
                title=dict(text=f"Esferas del Lote {st.session_state.lote_actual} – {prototipo_diag}", font=dict(size=20)),
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
    # --- FIN DEL DIAGRAMA INTERACTIVO ---