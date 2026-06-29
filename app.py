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

        if 'Fecha_Pago' in df.columns:
            df['Fecha_Pago'] = pd.to_datetime(df['Fecha_Pago'], errors='coerce')
            df['Fecha_Pago'] = df['Fecha_Pago'].dt.strftime('%d/%m/%Y %H:%M:%S').fillna('-')

        df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0)
        
        # INICIALIZACIÓN DE NUEVAS COLUMNAS (Compatibilidad con base de datos existente)
        if 'Pago_1' not in df.columns: df['Pago_1'] = 0.0
        if 'Pago_2' not in df.columns: df['Pago_2'] = 0.0
        if 'Fecha_Pago_2' not in df.columns: df['Fecha_Pago_2'] = '-'
        if 'Usuario_2' not in df.columns: df['Usuario_2'] = ''
        
        df['Pago_1'] = pd.to_numeric(df['Pago_1'], errors='coerce').fillna(0.0)
        df['Pago_2'] = pd.to_numeric(df['Pago_2'], errors='coerce').fillna(0.0)
        
        # Migración automática de datos viejos: Si estaba "Pagado" pero no tiene valor en Pago_1, se lo asignamos.
        df.loc[(df['Estado'] == 'Pagado') & (df['Pago_1'] == 0), 'Pago_1'] = df['Precio']

        return df
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
    "Pablo Barragán (Albañilería)",
    "Andrés (Albañileriá)",
    "Miguel Leyva (Instalaciones)",
    "José López (Pisos)",
    "Guillermo (Pintura)",
    "Gerardo Zamora (yaso y pintura)"
]

ANCHO_LOGIN_ENTRADAS = "200px"    
ESPACIO_ENTRE_RENGLONES = "8px"
TAMANO_LETRA_PAGADO = "14px"
GROSOR_ETIQUETA_PAGADO = "2px -25px"
TAMANO_LETRA_TABLA = "11px" # Reducido ligeramente para acomodar más columnas
TAMANO_LETRA_BOTONES = "12px"
COLOR_FONDO_PROTOTIPO = "#1E3A8A"
COLOR_TEXTO_PROTOTIPO = "#FFFFFF"

st.markdown(f"""
<style>
    div[data-testid="stTextInput"] {{
        max-width: {ANCHO_LOGIN_ENTRADAS} !important;
    }}
    .stSelectbox label, .stTextInput label {{
        font-size: {TAMANO_LETRA_TABLA} !important;
    }}
    .stButton > button {{
        font-size: {TAMANO_LETRA_BOTONES} !important;
        width: 100%;
    }}
    div[data-testid="stButton"] button {{
        padding: 1px 5px !important;
        font-size: 5px !important;
        height: auto !important;
    }}
    div[data-testid="stNumberInput"] input {{
        font-size: 11px !important;
        padding: 4px !important;
    }}
    [data-testid="stDataFrame"] {{
        display: flex;
        justify-content: center;
    }}
    [data-testid="stDataFrame"] div[data-testid="stTable"] th,
    [data-testid="stTable"] th {{
        text-align: center !important;
        justify-content: center !important;
    }}
    [data-testid="stDataFrame"] div[data-testid="stTable"] td,
    [data-testid="stTable"] td {{
        text-align: center !important;
    }}
</style>
""", unsafe_allow_html=True)

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

# Esta variable controlará unificadamente el Lote en TODAS las pestañas (se forza a string)
if 'lote_actual' not in st.session_state:
    st.session_state.lote_actual = str(df['Lote'].unique()[0]) if not df.empty else "1"

# Esta variable controla si en el mapa se están viendo "Todos"
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

@st.dialog("⚠️ CONFIRMACIÓN DE PAGO")
def dialogo_confirmacion(indice, lote, partida, destajista, precio, monto_pago, es_pago_2):
    st.warning(f"¿Confirmas el pago por **${monto_pago:,.2f}** de la partida **{partida}** para el **{lote}**?")
    if no es_pago_2:
        st.markdown(f"**Destajista asignado:** {destajista}")
    st.markdown(f"**Monto a liberar:** `${monto_pago:,.2f}`")
    
    col1, col2 = st.columns(2)
    if col1.button("✅ ACEPTAR"):
        ahora = datetime.now(ZoneInfo("America/Mexico_City"))
        fecha_hora_str = ahora.strftime("%d/%m/%Y %H:%M:%S")
        usuario_actual = st.session_state.usuario

        if es_pago_2:
            st.session_state.df.at[indice, 'Pago_2'] = monto_pago
            st.session_state.df.at[indice, 'Fecha_Pago_2'] = fecha_hora_str
            st.session_state.df.at[indice, 'Usuario_2'] = usuario_actual
        else:
            st.session_state.df.at[indice, 'Pago_1'] = monto_pago
            st.session_state.df.at[indice, 'Fecha_Pago'] = fecha_hora_str
            st.session_state.df.at[indice, 'Usuario'] = usuario_actual
            st.session_state.df.at[indice, 'Destajista'] = destajista
        
        # Recalcular Estado Global
        fila = st.session_state.df.loc[indice]
        pagado_tot = float(fila.get('Pago_1', 0)) + float(fila.get('Pago_2', 0))
        costo_tot = float(fila['Precio'])
        
        if pagado_tot >= costo_tot:
            st.session_state.df.at[indice, 'Estado'] = 'Pagado'
        else:
            st.session_state.df.at[indice, 'Estado'] = 'Pago Parcial'
            
        st.rerun()

    if col2.button("❌ CANCELAR"):
        st.rerun()

# --- MENÚ DE NAVEGACIÓN LATERAL ---
st.sidebar.title(f"👷 {st.session_state.usuario}")
menu = st.sidebar.radio("Menú Principal:", [
    "Registro de Destajos", 
    "Dashboard (Gráficos y Visor)", 
    "Mapa Interactivo",
    "Diagrama Interactivo"
])

# Control de estado de menú para forzar acciones al cambiar de pestaña
if 'menu_actual' not in st.session_state:
    st.session_state.menu_actual = menu

if st.session_state.menu_actual != menu:
    if menu == "Mapa Interactivo":
        st.session_state.mostrar_todos_mapa = True
    st.session_state.menu_actual = menu
    st.rerun()

if st.sidebar.button("💾 GUARDAR CAMBIOS"):
    with st.spinner("Sincronizando con Google..."):
        actualizar_datos_gsheet(st.session_state.df)
        st.session_state.df_original = st.session_state.df.copy()
        st.success("¡Datos guardados!")
        st.rerun()

if 'df_original' in st.session_state:
    if not st.session_state.df.equals(st.session_state.df_original):
        st.sidebar.warning("⚠️ Tienes cambios pendientes. ¡Presiona el botón Guardar!")

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state.usuario = None
    st.rerun()

def clave_ordenamiento(val):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(val))]

st.sidebar.markdown("---")
st.sidebar.markdown("### 🏗️ Resumen Total")

df_unicos = st.session_state.df[['Lote', 'Prototipo']].drop_duplicates()
resumen_df = df_unicos.groupby('Prototipo').size().reset_index(name='Cantidad')
resumen_df = resumen_df.sort_values(by='Prototipo', key=lambda x: x.map(clave_ordenamiento))

resumen_df_final = resumen_df.rename(columns={'Prototipo': 'Proto', 'Cantidad': 'Total'}).set_index('Proto')
st.sidebar.table(resumen_df_final)

total_general = resumen_df['Cantidad'].sum()
st.sidebar.markdown(f"**Total Prototipos: {total_general}**")    


# =========================================================================
# PESTAÑA 1: REGISTRO DE DESTAJOS
# =========================================================================
if menu == "Registro de Destajos":
    mostrar_cabecera_con_logo("📝 Control de Pagos Destajos")
    
    col_lote, col_fecha, col_vacio = st.columns([2 ,2 ,4])
    # Forzamos los valores a string para evitar errores de tipo al volver a la pestaña
    lotes_unicos = [str(x) for x in df['Lote'].unique()]
    
    # Sincronización maestra: Buscamos el índice del lote actual en la memoria
    lote_memoria = str(st.session_state.lote_actual)
    idx_t1 = lotes_unicos.index(lote_memoria) if lote_memoria in lotes_unicos else 0
    lote_activo = col_lote.selectbox("🔍 Selecciona el Lote:", lotes_unicos, index=idx_t1)
    
    # Si el usuario cambia el lote aquí, actualizamos la memoria maestra y recargamos
    if str(lote_activo) != lote_memoria:
        st.session_state.lote_actual = str(lote_activo)
        st.session_state.mostrar_todos_mapa = False
        st.rerun()
    
    fecha_filtro = col_fecha.date_input("📅 Filtrar por Fecha de Pago 1 (Opcional):", value=None, format="DD/MM/YYYY")

    # Filtramos usando texto para asegurar que encuentre el lote correctamente
    df_lote = df[df['Lote'].astype(str).str.strip() == str(lote_activo)]
    prototipo = df_lote['Prototipo'].iloc[0] if not df_lote.empty else "N/A"
    terreno = df_lote['Terreno_m2'].iloc[0] if not df_lote.empty else 0
    construccion = df_lote['Construccion_m2'].iloc[0] if not df_lote.empty else 0

    costo_total_filtrado = df_lote['Precio'].sum()
    df_lote_temp = df_lote.copy()
    df_lote_temp['Total_Pagado_Temp'] = pd.to_numeric(df_lote_temp.get('Pago_1', 0)) + pd.to_numeric(df_lote_temp.get('Pago_2', 0))
    pagado_filtrado = df_lote_temp['Total_Pagado_Temp'].sum()
    pendiente_filtrado = costo_total_filtrado - pagado_filtrado

    st.markdown(f"""
    <div style="background-color:{COLOR_FONDO_PROTOTIPO}; padding:20px; border-radius:10px; margin-bottom:20px; color:{COLOR_TEXTO_PROTOTIPO};">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.3); padding-bottom: 10px;">
            <div style="font-size:24px; font-weight:bold;">🏠 Lote {lote_activo} - Prototipo {prototipo}</div>
            <div style="font-size:16px;">📐 Terreno: {terreno} m² | Construcción: {construccion} m²</div>
        </div>
        <div style="display: flex; justify-content: space-between; gap: 15px; flex-wrap: wrap;">
            <div style="flex: 1; text-align: center; background-color:rgba(255,255,255,0.1); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Costo Total Prototipo en este Lote</div>
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
    
    st.markdown("##### ⏳ Filtros de Tabla")
    f_col1, f_col2, f_col3 = st.columns([2, 2, 2])
    filtro_concepto = f_col1.text_input("Buscar Concepto:", "", placeholder="Ej. Muros")
    filtro_destajista = f_col2.selectbox("Filtrar por Destajista:", ["Todos"] + LISTA_DESTAJISTAS)
    filtro_estado = f_col3.selectbox("Filtrar por Estado de Pago:", ["Todos", "Pendiente", "Pago Parcial", "Pagado"])
    
    df_filtrado = df_lote.copy()
    if filtro_concepto:
        df_filtrado = df_filtrado[df_filtrado['Partida'].str.contains(filtro_concepto, case=False, na=False)]
    if filtro_destajista != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Destajista'] == filtro_destajista]
    if filtro_estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Estado'] == filtro_estado]
    if fecha_filtro:
        df_filtrado = df_filtrado[df_filtrado['Fecha_Pago'] == str(fecha_filtro)]

    st.markdown("<br>", unsafe_allow_html=True)
    
    # NUEVA ESTRUCTURA DE COLUMNAS (12 Columnas proporcionadas)
    cols_weights = [2.2, 1.0, 1.8, 1.2, 0.6, 1.0, 1.0, 1.0, 1.0, 1.5, 1.0, 1.2]
    h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12 = st.columns(cols_weights)
    h1.markdown("<div style='font-size:11px;'>🗑️ **Partida**</div>", unsafe_allow_html=True)
    h2.markdown("<div style='font-size:11px;'>💵 **Costo**</div>", unsafe_allow_html=True)
    h3.markdown("<div style='font-size:11px;'>👷 **Destajista**</div>", unsafe_allow_html=True)
    h4.markdown("<div style='font-size:11px;'>💰 **Monto a pagar**</div>", unsafe_allow_html=True)
    h5.markdown("")
    h6.markdown("<div style='font-size:11px;'>💳 **Pago 1**</div>", unsafe_allow_html=True)
    h7.markdown("<div style='font-size:11px;'>📆 **Fecha 1**</div>", unsafe_allow_html=True)
    h8.markdown("<div style='font-size:11px;'>💳 **Pago 2**</div>", unsafe_allow_html=True)
    h9.markdown("<div style='font-size:11px;'>📆 **Fecha 2**</div>", unsafe_allow_html=True)
    h10.markdown("<div style='font-size:11px;'>📊 **Estado**</div>", unsafe_allow_html=True)
    h11.markdown("<div style='font-size:11px;'>🚨 **Por pagar**</div>", unsafe_allow_html=True)
    h12.markdown("<div style='font-size:11px;'>👤 **Usuario**</div>", unsafe_allow_html=True)
    st.markdown("<hr style='margin:5px 0 15px 0;'>", unsafe_allow_html=True)
    
    with st.container(height=550):
        if df_filtrado.empty:
            st.info("No hay partidas que coincidan con los filtros seleccionados.")
        else:
            for numero, (indice, fila) in enumerate(df_filtrado.iterrows(), start=1):
                c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12 = st.columns(cols_weights)
                
                precio = float(fila['Precio'])
                pago_1 = float(fila.get('Pago_1', 0))
                pago_2 = float(fila.get('Pago_2', 0))
                total_pagado = pago_1 + pago_2
                por_pagar = precio - total_pagado
                pct_pagado = min(100, int((total_pagado / precio) * 100)) if precio > 0 else 0
                
                # C1: Partida
                c1.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{numero}.- {fila['Partida']}</div>", unsafe_allow_html=True)
                # C2: Costo
                c2.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA}; text-align:center;'>${precio:,.2f}</div>", unsafe_allow_html=True)
                
                # C3: Destajista
                dest_val = fila.get('Destajista', '')
                if pago_1 > 0:
                    c3.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{dest_val}</div>", unsafe_allow_html=True)
                    destajista_seleccionado = dest_val
                else:
                    destajista_seleccionado = c3.selectbox("Destajista", ["Seleccionar..."] + LISTA_DESTAJISTAS, key=f"sel_{indice}", label_visibility="collapsed")
                
                # C4 y C5: Input Monto a Pagar y Botón
                if por_pagar > 0:
                    monto_input = c4.number_input("Monto", min_value=0.0, max_value=float(por_pagar), value=0.0, step=100.0, key=f"monto_{indice}", label_visibility="collapsed")
                    if c5.button("💳", key=f"btn_{indice}", type="primary", use_container_width=True):
                        if pago_1 == 0 and destajista_seleccionado == "Seleccionar...":
                            st.error("⚠️ Debes seleccionar un destajista primero para el Pago 1.")
                        elif monto_input <= 0:
                            st.error("⚠️ El monto a pagar debe ser mayor a 0.")
                        elif monto_input > por_pagar:
                            st.error("⚠️ La cantidad supera el monto máximo a pagar o no se admiten valores negativos.")
                        else:
                            es_pago_2 = (pago_1 > 0)
                            dialogo_confirmacion(indice, fila['Lote'], fila['Partida'], destajista_seleccionado, precio, monto_input, es_pago_2)
                else:
                    c4.markdown(f"<div style='text-align:center; color:gray; font-size:{TAMANO_LETRA_TABLA};'>Completado</div>", unsafe_allow_html=True)
                    c5.markdown("")
                
                # C6 y C7: Pago 1 y Fecha
                c6.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA}; text-align:center;'>${pago_1:,.2f}</div>", unsafe_allow_html=True)
                f1 = fila.get('Fecha_Pago', '-') if str(fila.get('Fecha_Pago', '')) != 'nan' else '-'
                c7.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: 10px; text-align:center;'>{f1}</div>", unsafe_allow_html=True)
                
                # C8 y C9: Pago 2 y Fecha
                c8.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA}; text-align:center;'>${pago_2:,.2f}</div>", unsafe_allow_html=True)
                f2 = fila.get('Fecha_Pago_2', '-') if str(fila.get('Fecha_Pago_2', '')) != 'nan' else '-'
                c9.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: 10px; text-align:center;'>{f2}</div>", unsafe_allow_html=True)
                
                # C10: Estado (Barra y Porcentaje)
                color_barra = "#10B981" if pct_pagado == 100 else "#3B82F6"
                barra_html = f"""
                <div style="width: 100%; background-color: #e5e7eb; border-radius: 4px; height: 18px; position: relative; margin-top: 2px;">
                    <div style="width: {pct_pagado}%; background-color: {color_barra}; height: 100%; border-radius: 4px;"></div>
                    <div style="position: absolute; top: 0; left: 0; width: 100%; text-align: center; font-size: 10px; color: {'white' if pct_pagado>50 else 'black'}; font-weight: bold; line-height: 18px;">Pagado al {pct_pagado}%</div>
                </div>
                """
                c10.markdown(barra_html, unsafe_allow_html=True)
                
                # C11: Por pagar
                color_deuda = "#EF4444" if por_pagar > 0 else "#10B981"
                c11.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA}; text-align:center; color:{color_deuda}; font-weight:bold;'>${por_pagar:,.2f}</div>", unsafe_allow_html=True)
                
                # C12: Usuario 1 / Usuario 2
                u1 = str(fila.get('Usuario', ''))
                u2 = str(fila.get('Usuario_2', ''))
                if u1 == 'nan': u1 = ''
                if u2 == 'nan': u2 = ''
                
                if u1 and u2: user_display = f"{u1} / {u2}"
                elif u1: user_display = u1
                else: user_display = "-"
                c12.markdown(f"<div style='font-size: 9px; text-align:center; margin-top:2px;'>{user_display}</div>", unsafe_allow_html=True)

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
        df_dash['Total_Pagado_Real'] = pd.to_numeric(df_dash['Pago_1']) + pd.to_numeric(df_dash['Pago_2'])
        
        monto_total = df_dash['Precio'].sum()
        monto_pagado = df_dash['Total_Pagado_Real'].sum()
        monto_pendiente = monto_total - monto_pagado
        
        df_pagados = df_dash[df_dash['Estado'] == 'Pagado'] # Solo las que llegaron al 100%
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
            
            # Gráfico con los 3 Estados Actualizados
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
            
            # Pie Chart ahora suma el Total Pagado Real
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
        "109": {"x": 453, "y": 813}, "110": {"x": 416, "y": 809}, "111": {"x": 383, "y": 804}, "112": {"x": 346, "y": 798},
        "113": {"x": 310, "y": 794}, "114": {"x": 274, "y": 789}, "115": {"x": 241, "y": 789}, "116": {"x": 207, "y": 782},
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
        df_lote_mapa = df[df['Lote'].astype(str).str.strip() == str(lote_num)].copy()
        
        if not df_lote_mapa.empty:
            total_partidas = len(df_lote_mapa)
            
            # Ahora calculamos el avance financieramente, no solo por cantidad de partidas
            df_lote_mapa['Total_Pagado_Real'] = pd.to_numeric(df_lote_mapa['Pago_1']) + pd.to_numeric(df_lote_mapa['Pago_2'])
            total_precio_lote = df_lote_mapa['Precio'].sum()
            total_pagado_lote = df_lote_mapa['Total_Pagado_Real'].sum()
            
            porcentaje = (total_pagado_lote / total_precio_lote * 100) if total_precio_lote > 0 else 0
            pagadas_completas = len(df_lote_mapa[df_lote_mapa['Estado'] == 'Pagado'])
            
            if porcentaje >= 99.9:
                color_lote = "🟢 Completado"
                hex_color = "#10B981"
            elif porcentaje > 0:
                color_lote = "🟡 En Proceso"
                hex_color = "#F59E0B"
            else:
                color_lote = "🔴 Pendiente"
                hex_color = "#EF4444"
                
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

    opciones_selector = ["Mostrar Todos"] + [f"Lote {k}" for k in COORDENADAS_LOTES.keys()]

    # Sincronización maestra para el Mapa
    if st.session_state.mostrar_todos_mapa:
        valor_defecto_mapa = "Mostrar Todos"
    else:
        valor_defecto_mapa = f"Lote {st.session_state.lote_actual}"
        
    idx_t3 = opciones_selector.index(valor_defecto_mapa) if valor_defecto_mapa in opciones_selector else 0

    if st.session_state.mostrar_todos_mapa:
        df_kpi = df.copy()
        titulo_kpi = "🏠 Proyecto General (Todos los Lotes)"
    else:
        lote_puro_kpi = str(st.session_state.lote_actual)
        df_kpi = df[df['Lote'].astype(str).str.strip() == lote_puro_kpi].copy()
        
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

    col_mapa, col_info_lote = st.columns([5, 3])

    with col_info_lote:
        c_titulo, c_selector = st.columns([5, 5])
        with c_titulo:
            st.markdown("### 📋 Desglose:")
        with c_selector:
            mapa_sel = st.selectbox("Selector", opciones_selector, index=idx_t3, label_visibility="collapsed")
            
            # Detectar cambios en el menú desplegable y actualizar la memoria global
            if mapa_sel != valor_defecto_mapa:
                if mapa_sel == "Mostrar Todos":
                    st.session_state.mostrar_todos_mapa = True
                else:
                    st.session_state.mostrar_todos_mapa = False
                    st.session_state.lote_actual = str(mapa_sel.replace("Lote ", ""))
                st.rerun()
        
        st.markdown("<hr style='margin-top:0px;'>", unsafe_allow_html=True)

        if not st.session_state.mostrar_todos_mapa:
            lote_puro_num = str(st.session_state.lote_actual)
            df_desglose_lote = df[df['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Precio']].copy()
            
            if not df_desglose_lote.empty:
                def formatear_estado_icono(val):
                    if val == "Pagado": return "🟢 100% PAGADO"
                    elif val == "Pago Parcial": return "🟡 PAGO PARCIAL"
                    return "🔴 PENDIENTE"
                    
                df_desglose_lote['Estatus'] = df_desglose_lote['Estado'].apply(formatear_estado_icono)
                
                styled_desglose = df_desglose_lote[['Partida', 'Estatus', 'Precio']].style.format({'Precio': '${:,.2f}'}).set_properties(**{'text-align': 'center'})
                
                st.dataframe(
                    styled_desglose,
                    use_container_width=True,
                    hide_index=True,
                    height=480
                )
            else:
                st.info(f"No se encontraron partidas para el lote {lote_puro_num}.")
        else:
            st.markdown("**Resumen General por Lote (Financiero):**")
            df_resumen_global = df.copy()
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
            
            st.dataframe(
                styled_global,
                use_container_width=True,
                hide_index=True,
                height=480
            )

    with col_mapa:
        fig_mapa = go.Figure()
        
        if os.path.exists("plano.png"):
            img_plano = Image.open("plano.png")
            ancho_img, alto_img = img_plano.size
            fig_mapa.add_layout_image(
                dict(
                    source=img_plano, xref="x", yref="y", x=0, y=0,
                    sizex=ancho_img, sizey=alto_img,
                    sizing="stretch", opacity=0.85, layer="below"
                )
            )
            fig_mapa.update_xaxes(range=[0, ancho_img], visible=False)
            fig_mapa.update_yaxes(range=[alto_img, 0], visible=False, scaleanchor="x")
        else:
            fig_mapa.update_xaxes(range=[0, 1000], visible=False)
            fig_mapa.update_yaxes(range=[1000, 0], visible=False, scaleanchor="x")

        if lotes_datos_mapa:
            df_mapa_puntos = pd.DataFrame(lotes_datos_mapa)
            
            if st.session_state.mostrar_todos_mapa:
                df_mostrar_puntos = df_mapa_puntos
                tamano_punto = 10
                modo_grafico = "markers" 
            else:
                id_buscado = str(st.session_state.lote_actual)
                df_mostrar_puntos = df_mapa_puntos[df_mapa_puntos['Lote_Id'] == id_buscado]
                tamano_punto = 26
                modo_grafico = "markers+text" 
                
                if not df_mostrar_puntos.empty:
                    target_x = df_mostrar_puntos.iloc[0]['x']
                    target_y = df_mostrar_puntos.iloc[0]['y']
                    fig_mapa.update_xaxes(range=[target_x - 180, target_x + 180])
                    fig_mapa.update_yaxes(range=[target_y + 180, target_y - 180]) 

            for _, item in df_mostrar_puntos.iterrows():
                fig_mapa.add_trace(go.Scatter(
                    x=[item['x']], y=[item['y']],
                    mode=modo_grafico,
                    marker=dict(size=tamano_punto, color=item['Hex'], line=dict(width=2, color='white')),
                    text=[item['Lote']], textposition="top center",
                    textfont=dict(size=14, color='black' if os.path.exists("plano.png") else 'white'),
                    hovertemplate=f"<b>{item['Lote']}</b><br>Estado: {item['Estado']}<br>Avance Financiero: {item['Avance']}<br>{item['Detalle']}<extra></extra>"
                ))

        fig_mapa.update_layout(
            showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            height=600,
            template="plotly_white"
        )
        st.plotly_chart(fig_mapa, use_container_width=True)

# =========================================================================
# PESTAÑA 4: DIAGRAMA INTERACTIVO (CON LEYENDA Y COLORES POR PARTIDA)
# =========================================================================
elif menu == "Diagrama Interactivo":
    mostrar_cabecera_con_logo("🔗 Diagrama Interactivo de Partidas", "Explora visualmente el avance financiero asignado por colores.")
    
    col_texto, col_selector = st.columns([6, 4])
    with col_texto:
        st.markdown("Selecciona un lote para ver sus partidas representadas como círculos. Cada partida tiene un **color único**.")
        st.markdown("👉 Los **círculos rellenos** representan partidas **pagadas al 100%**. <br>👉 Los **círculos huecos (solo con borde)** representan partidas **pendientes o parciales**.", unsafe_allow_html=True)
    
    with col_selector:
        # Aseguramos string aquí también
        lotes_diag = [str(x) for x in df['Lote'].unique()]
        
        # Sincronización maestra
        lote_memoria_diag = str(st.session_state.lote_actual)
        idx_t4 = lotes_diag.index(lote_memoria_diag) if lote_memoria_diag in lotes_diag else 0
        lote_seleccionado_diag = st.selectbox("Selecciona Lote a Explorar:", lotes_diag, index=idx_t4)
        
        # Si cambiamos el lote aquí, impacta todas las pestañas
        if str(lote_seleccionado_diag) != lote_memoria_diag:
            st.session_state.lote_actual = str(lote_seleccionado_diag)
            st.session_state.mostrar_todos_mapa = False
            st.rerun()

    df_lote_diag = df[df['Lote'].astype(str).str.strip() == str(lote_seleccionado_diag)]

    if not df_lote_diag.empty:
        
        # Generar Paleta de Colores Dinámica para cada partida distinta
        paleta_colores = px.colors.qualitative.Alphabet + px.colors.qualitative.Light24 + px.colors.qualitative.Dark24
        partidas_unicas = df_lote_diag['Partida'].unique()
        mapa_colores_partida = {partida: paleta_colores[i % len(paleta_colores)] for i, partida in enumerate(partidas_unicas)}

        num_partidas = len(df_lote_diag)
        cols = math.ceil(math.sqrt(num_partidas))

        x_coords = []
        y_coords = []
        colores_relleno = []
        colores_borde = []
        textos_hover = []

        for i, row in enumerate(df_lote_diag.itertuples()):
            x = i % cols
            y = i // cols
            x_coords.append(x)
            y_coords.append(y)

            estado = row.Estado
            costo = row.Precio
            pago_real = float(getattr(row, 'Pago_1', 0)) + float(getattr(row, 'Pago_2', 0))
            destajista = row.Destajista if pd.notna(row.Destajista) and row.Destajista != "" else "Sin Asignar"
            
            color_asignado = mapa_colores_partida[row.Partida]

            # Relleno vs Hueco según estado
            if estado == "Pagado":
                colores_relleno.append(color_asignado)
                colores_borde.append(color_asignado)
            else:
                colores_relleno.append("rgba(0,0,0,0)") # Hueco (transparente) para parcial o pendiente
                colores_borde.append(color_asignado)

            hover_text = f"<b>Partida:</b> {row.Partida}<br><b>Costo Total:</b> ${costo:,.2f}<br><b>Pagado:</b> ${pago_real:,.2f}<br><b>Destajista:</b> {destajista}<br><b>Estado:</b> {estado}"
            textos_hover.append(hover_text)

        # Calculo dinámico de la altura del gráfico para empatarlo con la leyenda
        altura_grafico = max(450, (math.ceil(num_partidas/cols) * 45))

        # Dividimos la pantalla: Izquierda el diagrama (60%), Derecha la Leyenda (40%)
        col_diagrama, col_leyenda = st.columns([6, 4])
        
        with col_diagrama:
            fig_diag = go.Figure(data=go.Scatter(
                x=x_coords,
                y=y_coords,
                mode='markers',
                marker=dict(
                    size=20, 
                    color=colores_relleno,
                    symbol='circle',
                    line=dict(width=3, color=colores_borde)
                ),
                text=textos_hover,
                hoverinfo='text'
            ))

            prototipo_diag = df_lote_diag['Prototipo'].iloc[0] if not df_lote_diag.empty else "N/A"

            fig_diag.update_layout(
                title=dict(text=f"Evaluando Lote {lote_seleccionado_diag} – Prototipo {prototipo_diag}", font=dict(size=20)),
                xaxis=dict(visible=False, showgrid=False, zeroline=False),
                yaxis=dict(visible=False, showgrid=False, zeroline=False, autorange="reversed"),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                height=altura_grafico, 
                # Ajuste del fondo negro con letras blancas en el tooltip:
                hoverlabel=dict(bgcolor="black", font_color="white", font_size=14, font_family="Arial") 
            )

            st.plotly_chart(fig_diag, use_container_width=True)
            
            pagadas_diag = len(df_lote_diag[df_lote_diag['Estado'] == 'Pagado'])
            pendientes_diag = num_partidas - pagadas_diag
            st.markdown(f"**🟢 Total Pagadas (100%):** {pagadas_diag} | **🔴 Pendientes/Parciales:** {pendientes_diag}")
            
        with col_leyenda:
            st.markdown("### 🎨 Leyenda de Partidas")
            st.markdown("Identifica cada burbuja por el color asignado a su partida correspondiente.", unsafe_allow_html=True)
            
            # Tabla de leyenda construida con HTML puro para que las esferas queden perfectas
            html_leyenda = "<table style='width:100%; border-collapse: collapse;'>"
            html_leyenda += "<tr><th style='text-align:center; border-bottom: 2px solid #ddd; padding: 10px;'>Color</th><th style='text-align:left; border-bottom: 2px solid #ddd; padding: 10px;'>Partida</th></tr>"
            
            # Formato en una sola línea para evitar la indentación y el error de bloque de código Markdown
            for partida, color in mapa_colores_partida.items():
                html_leyenda += f"<tr><td style='text-align:center; padding: 4px; border-bottom: 1px solid #eee;'><div style='width:20px; height:20px; border-radius:50%; background-color:{color}; margin:auto;'></div></td><td style='text-align:left; padding: 4px; border-bottom: 1px solid #eee; font-size: 14px;'>{partida}</td></tr>"
            html_leyenda += "</table>"

            # Encapsulamos la leyenda en un contenedor dinámico para igualar al gráfico con scroll
            with st.container(height=altura_grafico):
                st.markdown(html_leyenda, unsafe_allow_html=True)
        
    else:
        st.warning("⚠️ No hay partidas registradas para este lote.")