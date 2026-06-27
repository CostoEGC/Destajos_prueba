import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os
import re
import requests
import json
from zoneinfo import ZoneInfo
from PIL import Image

URL_API_SHEET = st.secrets["URL_API_SHEET"]

def obtener_datos_gsheet():
    try:
        response = requests.get(URL_API_SHEET)
        data = response.json()
        df = pd.DataFrame(data[1:], columns=data[0])

        if 'Fecha_Pago' in df.columns:
            df['Fecha_Pago'] = pd.to_datetime(df['Fecha_Pago'], errors='coerce')
            df['Fecha_Pago'] = df['Fecha_Pago'].dt.strftime('%d/%m/%Y %H:%M:%S')
            df['Fecha_Pago'] = df['Fecha_Pago'].fillna('-')

        df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0)
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
TAMANO_LETRA_TABLA = "14px"
TAMANO_LETRA_BOTONES = "12px"
COLOR_FONDO_PROTOTIPO = "#1E3A8A"
COLOR_TEXTO_PROTOTIPO = "#FFFFFF"
# =========================================================================

st.set_page_config(page_title="ERP Destajos EGC", layout="wide")

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

if 'usuario' not in st.session_state:
    st.session_state.usuario = None

def login():
    mostrar_cabecera_con_logo("🔐 Control de estimaciones", "Por favor, introduce tus credenciales para ingresar.")
    with st.container():
        usuario = st.text_input("Usuario", key="input_user")
        contrasena = st.text_input("Contraseña", type="password", key="input_pass")
        
        if st.button("Ingresar", use_container_width=False):
            usuarios_validos = st.secrets["usuarios"]
            if usuario in usuarios_validos and usuarios_validos[usuario] == contrasena:
                st.session_state.usuario = usuario
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos")

if st.session_state.usuario is None:
    login()
    st.stop()

if 'df' not in st.session_state:
    st.session_state.df = obtener_datos_gsheet()
    st.session_state.df_original = st.session_state.df.copy()

df = st.session_state.df

@st.dialog("⚠️ CONFIRMACIÓN DE PAGO")
def dialogo_confirmacion(indice, lote, partida, destajista, precio):
    st.warning(f"¿Confirmas el pago de la partida **{partida}** para el **{lote}**?")
    st.markdown(f"**Destajista asignado:** {destajista}")
    st.markdown(f"**Monto a liberar:** `${precio:,.2f}`")
    
    col1, col2 = st.columns(2)
    if col1.button("✅ ACEPTAR"):
        ahora = datetime.now(ZoneInfo("America/Mexico_City"))
        fecha_hora_str = ahora.strftime("%d/%m/%Y %H:%M:%S")
        usuario_actual = st.session_state.usuario

        st.session_state.df.at[indice, 'Estado'] = 'Pagado'
        st.session_state.df.at[indice, 'Destajista'] = destajista
        st.session_state.df.at[indice, 'Fecha_Pago'] = fecha_hora_str
        st.session_state.df.at[indice, 'Usuario'] = usuario_actual
        
        st.rerun()

    if col2.button("❌ CANCELAR"):
        st.rerun()

# --- MENÚ DE NAVEGACIÓN ---
st.sidebar.title(f"👷 {st.session_state.usuario}")
menu = st.sidebar.radio("Menú Principal:", ["Registro de Destajos", "Dashboard (Gráficos y Visor)", "Mapa Interactivo"])

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

st.sidebar.markdown("""
<style>
    [data-testid="stSidebar"] table { margin-left: auto; margin-right: auto; }
    [data-testid="stSidebar"] table th { text-align: center !important; }
    [data-testid="stSidebar"] table td { text-align: center !important; }
</style>
""", unsafe_allow_html=True)

total_general = resumen_df['Cantidad'].sum()
st.sidebar.markdown(f"**Total Prototipos: {total_general}**")    

# =========================================================================
# LÓGICA DE MEMORIA ENTRE PESTAÑAS Y SINCRONIZACIÓN
# =========================================================================
if 'tab1_lote' not in st.session_state:
    st.session_state.tab1_lote = df['Lote'].unique()[0] if not df.empty else None
if 'sync_push' not in st.session_state:
    st.session_state.sync_push = None

# =========================================================================
# PESTAÑA 1: REGISTRO DE DESTAJOS
# =========================================================================
if menu == "Registro de Destajos":
    mostrar_cabecera_con_logo("📝 Control de Pagos Destajos")
    
    col_lote, col_fecha, col_vacio = st.columns([2 ,2 ,4])
    lotes_unicos = df['Lote'].unique()
    
    # Mantener el lote donde nos quedamos
    idx_reg = 0
    if st.session_state.tab1_lote in lotes_unicos:
        idx_reg = list(lotes_unicos).index(st.session_state.tab1_lote)
        
    lote_activo = col_lote.selectbox("🔍 Selecciona el Lote:", lotes_unicos, index=idx_reg)
    
    # Sincronización en 1 dirección: Si el usuario cambia el lote AQUÍ, empujamos el cambio a las demás pestañas.
    if lote_activo != st.session_state.tab1_lote:
        st.session_state.tab1_lote = lote_activo
        st.session_state.sync_push = lote_activo
        st.rerun() # Recargamos para aplicar el cambio interno
    else:
        st.session_state.sync_push = None # Reseteamos el empuje para no forzar las otras pestañas eternamente

    fecha_filtro = col_fecha.date_input("📅 Filtrar por Fecha de Pago (Opcional):", value=None, format="DD/MM/YYYY")

    df_lote = df[df['Lote'] == lote_activo]
    prototipo = df_lote['Prototipo'].iloc[0] if not df_lote.empty else "N/A"
    terreno = df_lote['Terreno_m2'].iloc[0] if not df_lote.empty else 0
    construccion = df_lote['Construccion_m2'].iloc[0] if not df_lote.empty else 0

    costo_total_filtrado = df_lote['Precio'].sum()
    pagado_filtrado = df_lote[df_lote['Estado'] == 'Pagado']['Precio'].sum()
    pendiente_filtrado = df_lote[df_lote['Estado'] != 'Pagado']['Precio'].sum()

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
                <div style="font-size:14px; opacity: 0.9;">Total Pagado</div>
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
    filtro_estado = f_col3.selectbox("Filtrar por Estado de Pago:", ["Todos", "Pendiente", "Pagado"])
    
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
    h1, h2, h3, h4, h5, h6 = st.columns([4, 1.5, 3, 1.5, 2, 1.5])
    h1.markdown("🗑️ **Partida**")
    h2.markdown("💵 **Costo**")
    h3.markdown("👷 **Destajista/Contratista**")
    h4.markdown("📊 **Estado**")
    h5.markdown("📆 **Fecha Pago**")
    h6.markdown("👤 **Usuario**")
    st.markdown("<hr style='margin:5px 0 15px 0;'>", unsafe_allow_html=True)
    
    with st.container(height=450):
        if df_filtrado.empty:
            st.info("No hay partidas que coincidan con los filtros seleccionados.")
        else:
            for numero, (indice, fila) in enumerate(df_filtrado.iterrows(), start=1):
                c1, c2, c3, c4, c5, c6 = st.columns([4, 1.5, 3, 1.5, 2, 1.5])
                
                c1.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{numero}.- {fila['Partida']}</div>", unsafe_allow_html=True)
                c2.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>${fila['Precio']:,.2f}</div>", unsafe_allow_html=True)
                
                if fila['Estado'] == 'Pagado':
                    c3.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{fila['Destajista']}</div>", unsafe_allow_html=True)
                    c4.markdown(f"<div style='background-color:#10B981; color:white; padding:{GROSOR_ETIQUETA_PAGADO}; border-radius:4px; font-size:{TAMANO_LETRA_PAGADO}; text-align:center; margin-bottom:{ESPACIO_ENTRE_RENGLONES};'>🔒 PAGADO</div>", unsafe_allow_html=True)
                    c5.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{fila['Fecha_Pago']}</div>", unsafe_allow_html=True)
                    user_val = fila['Usuario'] if pd.notna(fila['Usuario']) else ""
                    c6.markdown(f"<div style='font-size: {TAMANO_LETRA_TABLA}; text-align:center;'>{user_val}</div>", unsafe_allow_html=True)
                else:
                    destajista_seleccionado = c3.selectbox(
                        "Destajista Dropdown", 
                        options=["Seleccionar..."] + LISTA_DESTAJISTAS,
                        key=f"sel_{indice}", 
                        label_visibility="collapsed"
                    )
                    if c4.button("P", key=f"btn_{indice}"):
                        if destajista_seleccionado == "Seleccionar...":
                            st.error("⚠️ Debes seleccionar un destajista primero.")
                        else:
                            dialogo_confirmacion(indice, fila['Lote'], fila['Partida'], destajista_seleccionado, fila['Precio'])
                    c5.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; text-align: center;'>—</div>", unsafe_allow_html=True)

# =========================================================================
# PESTAÑA 2: DASHBOARD
# =========================================================================
elif menu == "Dashboard (Gráficos y Visor)":
    mostrar_cabecera_con_logo("📊 Visor Estadístico e Indicadores")
    
    def ordenar_prototipos(val):
        match = re.search(r"(\d+)(.*)", str(val))
        if match:
            return (int(match.group(1)), match.group(2))
        return (float('inf'), str(val))

    st.markdown("### 🔍 Configuración de Evaluación")
    
    d_col1, d_col2 = st.columns(2)
    protos_disponibles = sorted(df['Prototipo'].unique(), key=ordenar_prototipos)
    lotes_disponibles = list(df['Lote'].unique())
    
    # Recibir el empuje de sincronización
    if st.session_state.sync_push and st.session_state.sync_push in lotes_disponibles:
        st.session_state.tab2_lotes = [st.session_state.sync_push]
        st.session_state.sync_push = None # Limpiar tras usar
        
    if 'tab2_lotes' not in st.session_state:
        st.session_state.tab2_lotes = lotes_disponibles
        
    protos_dash = d_col1.multiselect("Filtrar por Prototipos:", options=protos_disponibles, default=protos_disponibles)
    lotes_dash = d_col2.multiselect("Filtrar por Lotes:", options=lotes_disponibles, default=st.session_state.tab2_lotes)
    
    # Guardar estado local
    st.session_state.tab2_lotes = lotes_dash
    
    df_dash = df[(df['Lote'].isin(lotes_dash)) & (df['Prototipo'].isin(protos_dash))]
    
    if df_dash.empty:
        st.warning("⚠️ No hay datos para mostrar con los filtros seleccionados.")
    else:
        df_pagados = df_dash[df_dash['Estado'] == 'Pagado']
        df_pendientes = df_dash[df_dash['Estado'] != 'Pagado']
        
        monto_total = df_dash['Precio'].sum()
        monto_pagado = df_pagados['Precio'].sum()
        monto_pendiente = df_pendientes['Precio'].sum()
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("💰 Valor Total de Selección", f"${monto_total:,.2f}")
        
        if monto_total > 0:
            pct_pagado = (monto_pagado / monto_total) * 100
            pct_pendiente = (monto_pendiente / monto_total) * 100
        else:
            pct_pagado, pct_pendiente = 0, 0
            
        kpi2.metric("✅ Total Ejercido / Pagado", f"${monto_pagado:,.2f}", f"{pct_pagado:.2f}%")
        kpi3.metric("⏳ Por Pagar (Deuda)", f"${monto_pendiente:,.2f}", f"-{pct_pendiente:.2f}%", delta_color="inverse")
        
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("### 📋 Resumen Individual por Lote y Prototipo")
        
        df_dash_clean = df_dash.copy()
        df_dash_clean['Destajista'] = df_dash_clean['Destajista'].fillna('Sin Asignar')
        
        df_resumen = df_dash_clean.groupby(['Lote', 'Prototipo', 'Destajista', 'Estado'])['Precio'].sum().unstack(fill_value=0).reset_index()
        
        if 'Pagado' not in df_resumen.columns: df_resumen['Pagado'] = 0.0
        if 'Pendiente' not in df_resumen.columns: df_resumen['Pendiente'] = 0.0
        
        df_resumen['Total'] = df_resumen['Pagado'] + df_resumen['Pendiente']
        df_resumen = df_resumen[['Lote', 'Prototipo', 'Destajista', 'Total', 'Pagado', 'Pendiente']]
        df_resumen.columns = ['Lote', 'Prototipo', 'Destajista', 'Valor Total', 'Total Pagado', 'Deuda Pendiente']
        
        st.dataframe(
            df_resumen.style.format({
                'Valor Total': '${:,.2f}',
                'Total Pagado': '${:,.2f}',
                'Deuda Pendiente': '${:,.2f}'
            }), 
            use_container_width=True,
            hide_index=True
        )

        st.markdown("<br>", unsafe_allow_html=True)

        g_col1, g_col2 = st.columns(2)
        df_proto_graf = df_dash.groupby(['Prototipo', 'Estado'])['Precio'].sum().reset_index()
        fig_proto = px.bar(df_proto_graf, x='Prototipo', y='Precio', color='Estado', 
                           title="💼 Consolidado Financiero por Prototipo",
                           barmode='group', color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#EF4444'})
        g_col1.plotly_chart(fig_proto, use_container_width=True)
        
        df_lotes_graf = df_dash.groupby(['Lote', 'Estado'])['Precio'].sum().reset_index()
        fig_lote = px.bar(df_lotes_graf, x='Lote', y='Precio', color='Estado', 
                          title="🏘️ Avance Financiero por Lote",
                          color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#F59E0B'})
        g_col2.plotly_chart(fig_lote, use_container_width=True)

# =========================================================================
# PESTAÑA 3: MAPA INTERACTIVO
# =========================================================================
elif menu == "Mapa Interactivo":
    mostrar_cabecera_con_logo("🗺️ Plano Interactivo Dinámico", "Visualización gráfica del avance del desarrollo en tiempo real.")

    # --- COORDENADAS INTERNAS ---
    COORDENADAS_LOTES = {
        "1": {"x": 4577, "y": 3450},
        "2": {"x": 4721, "y": 3428},
        "3": {"x": 4851, "y": 3482},
        "4": {"x": 5081, "y": 3522},
        "5": {"x": 5211, "y": 3540},
        "6": {"x": 5321, "y": 3554},
        "7": {"x": 5325, "y": 3574},
        "8": {"x": 5439, "y": 3578},
        "9": {"x": 5561, "y": 3610},

        # Añade aquí los demás números...
    }

    lotes_datos_mapa = []
    for lote_num, coords in COORDENADAS_LOTES.items():
        df_lote_mapa = df[df['Lote'].astype(str).str.strip() == str(lote_num)]
        
        if not df_lote_mapa.empty:
            total_partidas = len(df_lote_mapa)
            pagadas = len(df_lote_mapa[df_lote_mapa['Estado'] == 'Pagado'])
            porcentaje = (pagadas / total_partidas) * 100 if total_partidas > 0 else 0
            
            if porcentaje == 100:
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
                "Detalle": f"{pagadas}/{total_partidas} Partidas"
            })

    opciones_selector = ["Mostrar Todos"] + [f"Lote {k}" for k in COORDENADAS_LOTES.keys()]

    # Recibir empuje de sincronización
    if st.session_state.sync_push:
        target = f"Lote {st.session_state.sync_push}"
        if target in opciones_selector:
            st.session_state.tab3_mapa = target
        st.session_state.sync_push = None
            
    if 'tab3_mapa' not in st.session_state:
        st.session_state.tab3_mapa = "Mostrar Todos"

    idx_mapa = 0
    if st.session_state.tab3_mapa in opciones_selector:
        idx_mapa = opciones_selector.index(st.session_state.tab3_mapa)

    # --- PANÉLES DE KPI EN LA PARTE SUPERIOR DEL MAPA ---
    if st.session_state.tab3_mapa == "Mostrar Todos":
        df_kpi = df.copy()
        titulo_kpi = "🏠 Proyecto General (Todos los Lotes)"
    else:
        lote_puro_kpi = st.session_state.tab3_mapa.replace("Lote ", "")
        df_kpi = df[df['Lote'].astype(str).str.strip() == lote_puro_kpi]
        titulo_kpi = f"🏠 Lote {lote_puro_kpi}"
        
    costo_total_mapa = df_kpi['Precio'].sum()
    pagado_mapa = df_kpi[df_kpi['Estado'] == 'Pagado']['Precio'].sum()
    pendiente_mapa = costo_total_mapa - pagado_mapa

    st.markdown(f"""
    <div style="background-color:{COLOR_FONDO_PROTOTIPO}; padding:20px; border-radius:10px; margin-bottom:20px; color:{COLOR_TEXTO_PROTOTIPO};">
        <div style="margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.3); padding-bottom: 10px;">
            <div style="font-size:24px; font-weight:bold;">{titulo_kpi}</div>
        </div>
        <div style="display: flex; justify-content: space-between; gap: 15px; flex-wrap: wrap;">
            <div style="flex: 1; text-align: center; background-color:rgba(255,255,255,0.1); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Costo Total</div>
                <div style="font-size:24px; font-weight:bold;">${costo_total_mapa:,.2f}</div>
            </div>
            <div style="flex: 1; text-align: center; background-color:rgba(16, 185, 129, 0.4); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Total Pagado</div>
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
        # Selector alineado a la derecha y más pequeño
        c_titulo, c_selector = st.columns([5, 5])
        with c_titulo:
            st.markdown("### 📋 Desglose:")
        with c_selector:
            # Selector sin etiqueta (para ahorrar espacio)
            lote_seleccionado_mapa = st.selectbox("Selector", opciones_selector, index=idx_mapa, label_visibility="collapsed")
            st.session_state.tab3_mapa = lote_seleccionado_mapa
        
        st.markdown("<hr style='margin-top:0px;'>", unsafe_allow_html=True)

        if lote_seleccionado_mapa != "Mostrar Todos":
            lote_puro_num = lote_seleccionado_mapa.replace("Lote ", "")
            df_desglose_lote = df[df['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Precio']]
            
            if not df_desglose_lote.empty:
                def formatear_estado_icono(val):
                    return "🟢 PAGADO" if val == "Pagado" else "⏳ PENDIENTE"
                    
                df_desglose_lote['Estatus'] = df_desglose_lote['Estado'].apply(formatear_estado_icono)
                
                st.dataframe(
                    df_desglose_lote[['Partida', 'Estatus', 'Precio']].style.format({'Precio': '${:,.2f}'}),
                    use_container_width=True,
                    hide_index=True,
                    height=480
                )
            else:
                st.info(f"No se encontraron partidas para el lote {lote_puro_num}.")
        else:
            # MOSTRAR TABLA GLOBAL RESUMIDA CUANDO SELECCIONAN "MOSTRAR TODOS"
            st.markdown("**Resumen General por Lote:**")
            
            # Calculamos las métricas globales
            df_resumen_global = df.groupby('Lote').agg(
                Total_Partidas=('Partida', 'count'),
                Pagadas=('Estado', lambda x: (x == 'Pagado').sum()),
                Costo_Total=('Precio', 'sum')
            ).reset_index()
            
            df_resumen_global['% Avance'] = (df_resumen_global['Pagadas'] / df_resumen_global['Total_Partidas']) * 100
            
            # Formateo estético
            df_resumen_global['% Avance'] = df_resumen_global['% Avance'].apply(lambda x: f"{x:.1f}%")
            
            st.dataframe(
                df_resumen_global.style.format({'Costo_Total': '${:,.2f}'}),
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
            
            # Lógica para cambiar tamaño de los puntos
            if lote_seleccionado_mapa == "Mostrar Todos":
                df_mostrar_puntos = df_mapa_puntos
                tamano_punto = 10
                modo_grafico = "markers" # Oculta el texto para que no se empalmen
            else:
                id_buscado = lote_seleccionado_mapa.replace("Lote ", "")
                df_mostrar_puntos = df_mapa_puntos[df_mapa_puntos['Lote_Id'] == id_buscado]
                tamano_punto = 26
                modo_grafico = "markers+text" # Muestra el texto cuando hay zoom
                
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
                    hovertemplate=f"<b>{item['Lote']}</b><br>Estado: {item['Estado']}<br>Avance: {item['Avance']}<br>{item['Detalle']}<extra></extra>"
                ))

        fig_mapa.update_layout(
            showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            height=600,
            template="plotly_white"
        )
        st.plotly_chart(fig_mapa, use_container_width=True)