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
from supabase import create_client, Client
import unicodedata

# =========================================================================
# CONFIGURACIÓN INICIAL DE LA PÁGINA Y CONEXIÓN A SUPABASE
# =========================================================================
# ESTA LÍNEA DEBE SER ESTRICTAMENTE LA PRIMERA DE STREAMLIT PARA EVITAR COLAPSOS
st.set_page_config(page_title="ERP Destajos EGC", layout="wide")

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

# Inicializar la conexión a la base de datos de Supabase
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def obtener_datos_gsheet():
    # 1. Definimos las columnas SIEMPRE al inicio
    mapeo_columnas = {
        'id': 'ID_DB', 
        'lote': 'Lote',
        'manzana': 'Manzana',
        'prototipo': 'Prototipo',
        'partida': 'Partida',
        'costo': 'Costo',
        'destajista': 'Destajista',
        'pct_adicional': '% Adicional',
        'pct_retencion': '% Retención',
        'monto_retenido': 'Monto Retenido',
        'estatus_retencion': 'Estatus Retención',
        'fecha_liberacion': 'Fecha Liberación',
        'usuario_libero': 'Usuario Liberó',
        'pagar': 'Pagar',
        'fecha_pago': 'Fecha pago',
        'usuario': 'Usuario'
    }

    # 2. Si aún no hay obra seleccionada (al cargar la página por primera vez), devolvemos la estructura vacía pero con los nombres de columnas
    if 'obra_actual' not in st.session_state or not st.session_state.obra_actual:
        return pd.DataFrame(columns=list(mapeo_columnas.values()))
        
    try:
        # 3. Conexión dinámica a la obra seleccionada
        tabla_dinamica = f"destajos_{str(st.session_state.obra_actual)}"
        #st.toast(f"🔍 El sistema está leyendo la tabla: {tabla_dinamica}")
        response = supabase.table(tabla_dinamica).select('*').order('id', desc=False).limit(50000).execute()
        datos = response.data
        
        # 4. Si la tabla de Supabase está vacía, igual devolvemos los encabezados
        if not datos:
            return pd.DataFrame(columns=list(mapeo_columnas.values()))
            
        df = pd.DataFrame(datos)
        df = df.rename(columns=mapeo_columnas)
        
        for col in ['% Adicional', '% Retención', 'Monto Retenido', 'Costo']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        df['Fecha pago'] = df['Fecha pago'].fillna('').astype(str).replace(['nan', 'None', '<NA>'], '').str.strip()
        df['Fecha Liberación'] = df['Fecha Liberación'].fillna('').astype(str).replace(['nan', 'None', '<NA>'], '').str.strip()
        df['Pagar'] = df['Pagar'].map(lambda x: True if str(x).lower() in ['true', '1', 'sí', 'si'] else False)
        df['Prototipo'] = df['Prototipo'].apply(lambda x: f"Prototipo {x}" if "Prototipo" not in str(x) else x)
        
        return df
    except Exception as e:
        st.error(f"Error al conectar con la base de datos de la obra: {e}")
        # Si falla, devolvemos la estructura de columnas para que no colapse la app
        return pd.DataFrame(columns=list(mapeo_columnas.values()))

def actualizar_datos_gsheet(df_envio):
    try:
        mapeo_inverso = {
            'ID_DB': 'id',
            'Lote': 'lote',
            'Manzana': 'manzana',
            'Prototipo': 'prototipo',
            'Partida': 'partida',
            'Costo': 'costo',
            'Destajista': 'destajista',
            '% Adicional': 'pct_adicional',
            '% Retención': 'pct_retencion',
            'Monto Retenido': 'monto_retenido',
            'Estatus Retención': 'estatus_retencion',
            'Fecha Liberación': 'fecha_liberacion',
            'Usuario Liberó': 'usuario_libero',
            'Pagar': 'pagar',
            'Fecha pago': 'fecha_pago',
            'Usuario': 'usuario'
        }
        
        df_db = df_envio.copy()
        
        cols_validas = [c for c in df_db.columns if c in mapeo_inverso.keys()]
        df_db = df_db[cols_validas]
        df_db = df_db.rename(columns=mapeo_inverso)
        
        # Limpieza de textos y fechas
        for col_str in ['fecha_pago', 'fecha_liberacion', 'usuario', 'usuario_libero', 'estatus_retencion', 'manzana', 'destajista']:
            if col_str in df_db.columns:
                df_db[col_str] = df_db[col_str].fillna('').astype(str).str.replace("'", "").replace(['nan', 'None', '<NA>'], '').str.strip()
        
        if 'id' in df_db.columns:
            # FILTRO A PRUEBA DE BALAS: Forzamos el ID a número. Si es nulo, NaN o texto, será considerado "nueva partida"
            es_nueva = pd.to_numeric(df_db['id'], errors='coerce').isna()
            
            df_nuevas = df_db[es_nueva].drop(columns=['id'])
            df_existentes = df_db[~es_nueva]
            
            nuevas = df_nuevas.to_dict(orient='records')
            existentes = df_existentes.to_dict(orient='records')
            
            # Función auxiliar para purificar los datos (Supabase rechaza tipos de dato de Numpy)
            def purificar_registro(registro):
                r_limpio = {}
                for k, v in registro.items():
                    if pd.isna(v):
                        r_limpio[k] = None
                    # Si es un tipo de dato de Numpy, lo forzamos a tipo nativo de Python usando .item()
                    elif hasattr(v, 'item'):
                        r_limpio[k] = v.item()
                    else:
                        r_limpio[k] = v
                return r_limpio

            nuevas_limpias = [purificar_registro(r) for r in nuevas]
            
            existentes_limpias = []
            for r in existentes:
                r_l = purificar_registro(r)
                if r_l.get('id') is not None:
                    r_l['id'] = int(r_l['id'])  # Obligamos a que el ID sea entero
                existentes_limpias.append(r_l)
            
            tabla_dinamica = f"destajos_{st.session_state.obra_actual}"
            # Inyección a Supabase
            if nuevas_limpias:
                supabase.table(tabla_dinamica).insert(nuevas_limpias).execute()
            if existentes_limpias:
                supabase.table(tabla_dinamica).upsert(existentes_limpias).execute()
        else:
            registros = df_db.to_dict(orient='records')
            registros_limpios = [purificar_registro(r) for r in registros]
            if registros_limpios:
                supabase.table(tabla_dinamica).insert(registros_limpios).execute()
            
    except Exception as e:
        st.error(f"Error técnico al sincronizar con Supabase: {e}")


# =========================================================================
# ⚙️ CONFIGURACIÓN DE DISEÑO Y VARIABLES GLOBALES
# =========================================================================
LISTA_DESTAJISTAS_BASE = [
    "Pablo Barragán (Albañilería)",
    "Andrés (Albañilería)",
    "Miguel Leyva (Instalaciones)",
    "José López (Pisos)",
    "Guillermo (Pintura)",
    "Gerardo Zamora (Yeso y pintura)"
]
LISTA_DESTAJISTAS = [" "] + sorted(LISTA_DESTAJISTAS_BASE)

# =========================================================================
# LISTA MAESTRA EXTRAÍDA DEL EXCEL (Sin números, orden exacto)
# =========================================================================
ORDEN_PARTIDAS_MAESTRO = [
    "Trazo de cimentacion, muros e instalaciones",
    "Cisterna",
    "Excavaciones drenaje y cimentacion",
    "Cimbra losa de cimentacion",
    "Nivelacion de plataformas",
    "Acero losa de cimentacion",
    "Concreto en cimentacion",
    "Instalaciones losa de cimentacion",
    "Muros planta baja",
    "Muros bajo escalera",
    "Castillos, dalas y cerramientos pb",
    "Muros de concreto en pb",
    "Muros reforzados pb",
    "Instalaciones en muros p.b.",
    "Muro lateral cochera",
    "Muros y castillos en patio de servicio",
    "Instalacion hidraulica y electrica en patio",
    "Cimbra en losa de entrepiso 1",
    "Acero en losa de entrepiso 1",
    "Concreto en losa de entrepiso 1",
    "Instalaciones losa de entrepiso 1",
    "Escalera de pb-n1",
    "Muros nivel 1",
    "Castillos, dalas y cerramientos nivel1",
    "Muros de reforzados en nivel 1",
    "Muros de concreto en nivel 1",
    "Instalaciones en muros n1",
    "Cimbra en losa de entrepiso 2",
    "Acero en losa de entrepiso 2",
    "Concreto en losa de entrepiso 2",
    "Hormigon en losa de entrepiso 2",
    "Veneciano en terraza",
    "Instalaciones en losa de entrepiso 2",
    "Escalera de n1-n2",
    "Muros nivel 2",
    "Castillos, dalas y cerramientos nivel2",
    "Muros de concreto en nivel 2",
    "Instalaciones en muros n2",
    "Cimbra en losa de entrepiso 3",
    "Acero en losa de entrepiso 3 inc. pretiles",
    "Concreto en losa de entrepiso 3",
    "Instalaciones en losa entrepiso 3",
    "Albañilerias en azotea y terraza",
    "Subcontrato por impermeabilizacion de azotea",
    "Apalillado en azotea",
    "Estructura tinaco",
    "Instalaciones de gas y calentador solar",
    "Subcontrato por aplanados de yeso y pasta",
    "Base para cocina",
    "Aplanados en baños",
    "Zarpeos en losas y castillos",
    "Recibir instalaciones de luz, agua",
    "Guiado de ductos",
    "Resane en balcon de nivel 1",
    "Sardinel en balcon de nivel 1",
    "Colocacion de monomandos en regaderas",
    "Repison medio baño planta baja",
    "Forjado de nicho en escalera",
    "Albañilerias de patio y muro medianero",
    "Aplanado de patio",
    "Albañilerias en cochera",
    "Base para cuadro de medicion hidraulico",
    "Huellas vehiculares en cochera",
    "Limpieza en patio",
    "Instalacion de base medidor electrico",
    "Instalacion de cuadro de medicion hidraulico",
    "Encofrado de tuberia en patio",
    "Forjado de registro pluvial en cochera",
    "Resane de llave de chorro en cochera",
    "Abultado en ventanas",
    "Aplanados fachadas ppal",
    "Junta fachada ppal",
    "Aplanados fachada posterior",
    "Junta fachada posterior",
    "Pisos y azulejos",
    "Recubrimientos en fachada ppal",
    "Terminacion de zoclo",
    "Elaboracion de sardinel en baños",
    "Forjado de jaboneras en area de regaderas",
    "Nivelacion de charolas de baños",
    "Subcontrato por aplicacion de fondo en fachada principal",
    "Subcontrato por aplicacion de pintura 1° mano en fachada principal",
    "Subcontrato por aplicacion de pintura 2° mano en fachada principal",
    "Subcontrato por aplicacion de fondo en fachada posterior",
    "Subcontrato por aplicacion de pintura 1° mano en fachada posterior",
    "Subcontrato por aplicacion de pintura 2° mano en fachada posterior",
    "Subcontrato por aplicacion de fondo en interiores",
    "Subcontrato por aplicacion de pintura 1° mano en interiores",
    "Subcontrato por aplicacion de pintura 2° mano en interiores",
    "Subcontrato de tablaroca y durock en muros y plafones",
    "Subcontrato de ventaneria de aluminio y vidrio iva cero",
    "Barandales de herreria en escalera",
    "Fabricacion de escalera marina",
    "Herreria para rejillas en cocheras y patios",
    "Subcontrato por fabricacion y colocacion de barra desayunadora a base de herreria",
    "Subcontrato de barandal de herreria entre escalera entre sala",
    "Subcontrato de canceles de baño iva cero",
    "Subcontrato por topes de aluminio iva cero",
    "Subcontrato por numeros de aluminio iva cero",
    "Subcontrato por barandales de cristal en balcones iva cero",
    "Subcontrato por barandales de cristal en terraza iva cero",
    "Subcontrato domos iva cero",
    "Colocacion de escalera marina",
    "Subcontrato por suministro e instalacion de cocina integral, closets, muebles de baño. cocina con granito gris, madera en melamina deacuerdo a plano, incluye: tarja, contracanasta, estufa, campana",
    "Pata granito itaunas",
    "Splash granito itaunas",
    "Subcontrato de carpinteria para puertas madera",
    "Suministro de tierra vegetal",
    "Suministro y colocacion de pasto en rollo cochera y patio",
    "Colocacion de accesorios para baño",
    "Amueblado hidraulico y sanitario",
    "Amueblado electrico",
    "Limpieza gruesa 1 y retiro de escombro fuera de obra",
    "Limpieza gruesa de cisterna",
    "Subcontrato de laboratorio de control de calidad",
    "Detallado de vivienda y garantias",
    "Limpieza gruesa 2 y retiro de escombro fuera de obra",
    "Prueba general sanitaria, hidraulica y pluvial",
    "Instalacion de bomba, boyler, tanque y toma de gas",
    "Instalacion para aire acondicionado",
    "Cableado aire acondicionado",
    "Base para boiler",
    "Limpieza fina de cisterna",
    "Guiado telmex de registro a casa",
    "Retiro medidor hidráulico",
    "Colocacion de medidor hidraulico",
    "Colocacion de tinaco y ramaleo de tuberias",
    "Colocacion de tanque y control press con alimentacion electrica",
    "Conexión de toma de gas a tanque estacionario",
    "Alimentacion electrica para bomba sumergible y tanque presurizado 5 hilos",
    "Alimentacion de registro a vivienda (ponchado)"
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

def sort_prototipos(p):
    # Separa el número, la letra y el signo + para ordenar perfectamente (1, 1+, 2, 2+, 2A, 2A+)
    p_str = str(p).replace("Prototipo ", "").strip()
    match = re.match(r"(\d+)([a-zA-Z]*)(\+?)", p_str)
    if match:
        num = int(match.group(1))
        letra = match.group(2).lower()
        plus = 1 if match.group(3) == '+' else 0
        return (num, letra, plus)
    return (999, p_str, 0)

def normalizar_texto(texto):
    """Pasa a minúsculas, quita espacios extra y elimina acentos para cruzar datos perfectos"""
    if pd.isna(texto): return ""
    texto = str(texto).strip().lower()
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')    


def extraer_numero_partida(partida_str):
    """Extrae el número inicial de la partida (solo se usa en secreto para ordenar)."""
    match = re.search(r'^(\d+)', str(partida_str).strip())
    return int(match.group(1)) if match else 99999

def limpiar_texto_partida(partida_str):
    """Elimina el número y guiones para que en pantalla solo aparezcan las palabras."""
    return re.sub(r'^\d+[\s\.\-]*', '', str(partida_str)).strip()

def obtener_conceptos_ordenados_limpios(df_fuente):
    """Extrae las partidas, las ordena por su número oculto y devuelve solo el texto limpio sin duplicados."""
    df_temp = df_fuente[['Partida']].drop_duplicates().copy()
    df_temp['Num'] = df_temp['Partida'].apply(extraer_numero_partida)
    df_temp = df_temp.sort_values('Num')
    limpios = df_temp['Partida'].apply(limpiar_texto_partida).unique().tolist()
    return [c for c in limpios if str(c).strip()]

# =========================================================================
# INICIALIZACIÓN DE ESTADOS (MEMORIA ABSOLUTA DEL SISTEMA)
# =========================================================================
if 'usuario' not in st.session_state: st.session_state.usuario = None
if 'obra_actual' not in st.session_state: st.session_state.obra_actual = None
if 'df' not in st.session_state:
    st.session_state.df = obtener_datos_gsheet()
    st.session_state.df_original = st.session_state.df.copy()

if 'grid_key' not in st.session_state: st.session_state.grid_key = 0
if 'current_grid_state' not in st.session_state: st.session_state.current_grid_state = pd.DataFrame()
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
    col_izq, col_centro, col_der = st.columns([1.2, 1, 1.2])
    with col_centro:
        st.markdown("<br>", unsafe_allow_html=True)
        usuario = st.text_input("Usuario", key="input_user")
        contrasena = st.text_input("Contraseña", type="password", key="input_pass")
        
        # --- LISTA DESPLEGABLE DE OBRAS DISPONIBLES ---
        lista_obras = [" ", "Portofino(N64)", "Ravello(N76)", "Etapa8(NX)"] # Añade aquí tus futuras obras
        obra_seleccionada = st.selectbox("Selecciona la Obra:", options=lista_obras)
        
        if st.button("Ingresar", use_container_width=True, type="primary"):
            usuarios_validos = st.secrets["usuarios"] if "usuarios" in st.secrets else {}
            if usuario in usuarios_validos and usuarios_validos[usuario] == contrasena:
                st.session_state.usuario = usuario
                st.session_state.obra_actual = obra_seleccionada # Guardamos la obra elegida
                
                # Cargamos los datos de esa obra específica antes de entrar
                with st.spinner(f"Conectando a base de datos de {obra_seleccionada}..."):
                    st.session_state.df = obtener_datos_gsheet()
                    st.session_state.df_original = st.session_state.df.copy()
                    
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos")

# Detenemos la app si falta el usuario O si falta la obra
if st.session_state.usuario is None or st.session_state.get('obra_actual') is None:
    login()
    st.stop()

# --- MENÚ DE NAVEGACIÓN LATERAL ---
st.sidebar.markdown(f"<h3 style='margin-bottom: -15px; color: #3B82F6; font-weight: bold;'>🏢 Obra: {st.session_state.obra_actual}</h3>", unsafe_allow_html=True)
st.sidebar.title(f"👷 {st.session_state.usuario}")
menu = st.sidebar.radio("Menú Principal:", [
    "Registro de Destajos", 
    "Fondo de Garantía (Retenciones)", 
    "Dashboard (Gráficos y Visor)", 
    "Mapa Interactivo",
    "Visor Móvil"
])

if 'menu_actual' not in st.session_state:
    st.session_state.menu_actual = menu

if st.session_state.menu_actual != menu:
    if 'current_grid_state' in st.session_state and not st.session_state.current_grid_state.empty:
        df_vivo = st.session_state.current_grid_state
        for _, row in df_vivo.iterrows():
            idx_orig = int(row['_original_index'])
            for col in df_vivo.columns:
                if col in st.session_state.df.columns and col != '_original_index':
                    st.session_state.df.at[idx_orig, col] = row[col]
                    
    for key in list(st.session_state.keys()):
        if key.startswith('sel_') or key.startswith('rep_'):
            st.session_state[key] = st.session_state[key]
            
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
        # 1. Limpiamos y preparamos los datos
        df_actual_pantalla['Pagar_Bool'] = df_actual_pantalla['Pagar'].astype(str).str.lower().isin(['true', '1'])
        df_actual_pantalla['Fecha_Pago_Limpia'] = df_actual_pantalla['Fecha pago'].fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>'], '')
        df_actual_pantalla['Destajista_Limpio'] = df_actual_pantalla['Destajista'].fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>'], '')
        
        # Filtramos solo las filas que aún no están pagadas (pendientes)
        pendientes = df_actual_pantalla[df_actual_pantalla['Fecha_Pago_Limpia'] == '']
        
        # 2. LÓGICA DE BLOQUEO (Las dos reglas obligatorias)
        error_1 = pendientes[(pendientes['Pagar_Bool'] == True) & (pendientes['Destajista_Limpio'] == '')]
        error_2 = pendientes[(pendientes['Pagar_Bool'] == False) & (pendientes['Destajista_Limpio'] != '')]
        
        if not error_1.empty:
            st.sidebar.error("❌ ¡ALTO! Hay filas con la casilla de Pagar activada pero SIN destajista. Completa el dato y haz clic en 'Actualizar Totales' antes de guardar.")
        elif not error_2.empty:
            st.sidebar.error("❌ ¡ALTO! Asignaste un destajista a una fila pero NO activaste su casilla de Pagar. Activa la casilla y haz clic en 'Actualizar Totales' antes de guardar.")
        else:
            with st.spinner("Sincronizando con Supabase..."):
                tz_mx = ZoneInfo("America/Mexico_City")
                tiempo_actual = datetime.now(tz_mx)
                meses_3_letras = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
                dia = tiempo_actual.strftime("%d")
                mes = meses_3_letras[tiempo_actual.month]
                anio = tiempo_actual.strftime("%Y")
                hora = tiempo_actual.strftime("%H:%M:%S")
                ahora = f"{dia}/{mes}/{anio} {hora}"
                usuario_actual = st.session_state.usuario
                
                filas_a_pagar = pendientes[pendientes['Pagar_Bool'] == True]
                
                if not filas_a_pagar.empty:
                    for _, row in filas_a_pagar.iterrows():
                        idx_original = int(row['_original_index'])
                        st.session_state.df.at[idx_original, 'Destajista'] = str(row['Destajista']).strip()
                        st.session_state.df.at[idx_original, 'Pagar'] = True
                        st.session_state.df.at[idx_original, 'Fecha pago'] = ahora
                        st.session_state.df.at[idx_original, 'Usuario'] = usuario_actual
                
                for col_num in ['% Adicional', '% Retención', 'Monto Retenido', 'Costo']:
                    if col_num in st.session_state.df.columns:
                        st.session_state.df[col_num] = pd.to_numeric(st.session_state.df[col_num], errors='coerce').fillna(0).astype(float)

                for _, row in df_actual_pantalla.iterrows():
                    idx_original = int(row['_original_index'])
                    st.session_state.df.loc[idx_original, 'Destajista'] = str(row['Destajista']).strip() if pd.notna(row['Destajista']) else ""
                    
                    pct_ad = float(row['% Adicional']) if pd.notna(row['% Adicional']) else 0.0
                    pct_ret = float(row['% Retención']) if pd.notna(row['% Retención']) else 0.0
                    costo_orig = float(row['Costo']) if pd.notna(row['Costo']) else 0.0
                    
                    st.session_state.df.loc[idx_original, '% Adicional'] = pct_ad
                    st.session_state.df.loc[idx_original, '% Retención'] = pct_ret
                    
                    if pct_ret > 0:
                        st.session_state.df.loc[idx_original, 'Monto Retenido'] = costo_orig * pct_ret
                        if str(st.session_state.df.loc[idx_original, 'Estatus Retención']).strip() == "":
                            st.session_state.df.loc[idx_original, 'Estatus Retención'] = "Retenido"
                    else:
                        st.session_state.df.loc[idx_original, 'Monto Retenido'] = 0.0
                        st.session_state.df.loc[idx_original, 'Estatus Retención'] = ""
                        
                if not filas_a_pagar.empty:
                    for _, row in filas_a_pagar.iterrows():
                        idx_original = int(row['_original_index'])
                        st.session_state.df.loc[idx_original, 'Pagar'] = True
                        st.session_state.df.loc[idx_original, 'Fecha pago'] = ahora
                        st.session_state.df.loc[idx_original, 'Usuario'] = usuario_actual

                df_envio = st.session_state.df.copy()
                if 'Concepto_Limpio' in df_envio.columns:
                    df_envio = df_envio.drop(columns=['Concepto_Limpio'])

                df_envio['Fecha pago'] = df_envio['Fecha pago'].apply(lambda x: f"'{x}" if str(x).strip() != '' else '')
                
                actualizar_datos_gsheet(df_envio)
                
                st.session_state.df = obtener_datos_gsheet()
                st.session_state.df_original = st.session_state.df.copy()
                st.session_state.current_grid_state = pd.DataFrame() 
                st.session_state.grid_key += 1 
                st.session_state.reload_trigger = True
                
                # --- NUEVO: GUARDAR FECHA DE ÉXITO EN MEMORIA ---
                st.session_state.ultima_vez_guardado = f"{dia}/{mes}/{anio} {hora}"
                
                st.sidebar.success("✅ ¡Cambios guardados con éxito!")
                st.rerun()

# --- NUEVO: MOSTRAR LA FECHA DEL ÚLTIMO GUARDADO Y LA ALERTA DE CAMBIOS ---
if st.session_state.get('ultima_vez_guardado'):
    st.sidebar.markdown(f"<div style='text-align: center; color: #10B981; font-size: 14px; margin-top: -10px; margin-bottom: 15px;'>Último guardado:<br><b>✅ {st.session_state.ultima_vez_guardado}</b></div>", unsafe_allow_html=True)
    
# Este es el contenedor vacío donde aparece la advertencia amarilla al tocar la tabla
if 'alerta_cambios_ui' not in st.session_state:
    alerta_cambios_ui = st.sidebar.empty()
else:
    alerta_cambios_ui = st.sidebar.empty()

@st.dialog("🖨️ Generar Reporte de Pagos", width="large")
def dialogo_reportes():
    st.markdown("### 📊 Configurar Filtros para el Reporte PDF")
    st.write("Selecciona los criterios específicos que deseas plasmar en el documento impreso.")
    
    df_base_rep = st.session_state.df.copy()
    
    # --- NUEVO: FILTROS EN CASCADA PARA REPORTES Y ORDEN MAESTRO ---
    df_base_rep['Concepto_Limpio'] = df_base_rep['Partida'].apply(limpiar_texto_partida)

    # Obtenemos lo que el usuario ya seleccionó (si está vacío, no filtra)
    curr_proto = st.session_state.get('rep_sel_proto', [])
    curr_mz = st.session_state.get('rep_sel_manzana', [])
    curr_lotes = st.session_state.get('rep_sel_lotes', [])
    curr_concepto = st.session_state.get('rep_sel_concepto', [])
    curr_dest = st.session_state.get('rep_sel_dest', [])

    # 1. Prototipos
    df_proto = df_base_rep.copy()
    if curr_mz: df_proto = df_proto[df_proto['Manzana'].isin(curr_mz)]
    if curr_lotes: df_proto = df_proto[df_proto['Lote'].astype(str).isin(curr_lotes)]
    if curr_concepto: df_proto = df_proto[df_proto['Concepto_Limpio'].isin(curr_concepto)]
    if curr_dest: df_proto = df_proto[df_proto['Destajista'].isin(curr_dest)]
    list_prototipos = sorted(df_proto['Prototipo'].unique().tolist(), key=sort_prototipos)

    # 2. Manzanas
    df_mz = df_base_rep.copy()
    if curr_proto: df_mz = df_mz[df_mz['Prototipo'].isin(curr_proto)]
    if curr_lotes: df_mz = df_mz[df_mz['Lote'].astype(str).isin(curr_lotes)]
    if curr_concepto: df_mz = df_mz[df_mz['Concepto_Limpio'].isin(curr_concepto)]
    if curr_dest: df_mz = df_mz[df_mz['Destajista'].isin(curr_dest)]
    list_manzanas = sorted([x for x in df_mz['Manzana'].unique().tolist() if str(x).strip()], key=natural_sort_key)

    # 3. Lotes
    df_lote = df_base_rep.copy()
    if curr_proto: df_lote = df_lote[df_lote['Prototipo'].isin(curr_proto)]
    if curr_mz: df_lote = df_lote[df_lote['Manzana'].isin(curr_mz)]
    if curr_concepto: df_lote = df_lote[df_lote['Concepto_Limpio'].isin(curr_concepto)]
    if curr_dest: df_lote = df_lote[df_lote['Destajista'].isin(curr_dest)]
    list_lotes = sorted([str(x) for x in df_lote['Lote'].unique().tolist() if str(x).strip()], key=natural_sort_key)

    # 4. Concepto / Partida (Aplicando el ORDEN_PARTIDAS_MAESTRO)
    df_conc = df_base_rep.copy()
    if curr_proto: df_conc = df_conc[df_conc['Prototipo'].isin(curr_proto)]
    if curr_mz: df_conc = df_conc[df_conc['Manzana'].isin(curr_mz)]
    if curr_lotes: df_conc = df_conc[df_conc['Lote'].astype(str).isin(curr_lotes)]
    if curr_dest: df_conc = df_conc[df_conc['Destajista'].isin(curr_dest)]
    conceptos_presentes = [str(c).strip() for c in df_conc['Concepto_Limpio'].unique() if str(c).strip()]
    list_conceptos = sorted(conceptos_presentes, key=lambda x: ORDEN_PARTIDAS_MAESTRO.index(x) if x in ORDEN_PARTIDAS_MAESTRO else 99999)

    # 5. Destajistas
    df_dest = df_base_rep.copy()
    if curr_proto: df_dest = df_dest[df_dest['Prototipo'].isin(curr_proto)]
    if curr_mz: df_dest = df_dest[df_dest['Manzana'].isin(curr_mz)]
    if curr_lotes: df_dest = df_dest[df_dest['Lote'].astype(str).isin(curr_lotes)]
    if curr_concepto: df_dest = df_dest[df_dest['Concepto_Limpio'].isin(curr_concepto)]
    list_destajistas_filtro = sorted([str(d) for d in df_dest['Destajista'].unique() if str(d).strip()], key=natural_sort_key)
    # -----------------------------------------------------------------

    r_col1, r_col2 = st.columns(2)
    with r_col1:
        st.multiselect("Prototipo(s):", options=list_prototipos, placeholder="Todos", key="rep_sel_proto")
        st.multiselect("Lote(s):", options=list_lotes, placeholder="Todos", key="rep_sel_lotes")
        st.multiselect("Concepto / Partida:", options=list_conceptos, placeholder="Todos", key="rep_sel_concepto")
    with r_col2:
        st.multiselect("Manzana(s):", options=list_manzanas, placeholder="Todas", key="rep_sel_manzana")
        
        # --- NUEVO: Checkboxes para Estado de Pago ---
        st.markdown("<span style='font-size: 14px;'>Estado de Pago:</span>", unsafe_allow_html=True)
        c_chk1, c_chk2 = st.columns(2)
        with c_chk1:
            chk_pagado = st.checkbox("Pagado", value=True, key="rep_chk_pagado")
        with c_chk2:
            chk_por_pagar = st.checkbox("Por pagar", value=True, key="rep_chk_por_pagar")
        # ---------------------------------------------
        
        st.multiselect("Destajista(s):", options=list_destajistas_filtro, placeholder="Todos", key="rep_sel_dest")
        
    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

    col_izq_fechas, col_der_impresion = st.columns(2)
    
    with col_izq_fechas:
        st.markdown("##### 📅 Filtrar por Rango de Fechas")
        rango = st.date_input("Selecciona el período:", value=[], key="rep_rango_fechas", label_visibility="collapsed")
        
    with col_der_impresion:
        st.markdown("##### 📑 Opciones de Impresión")
        col_chk, col_sel = st.columns([1.1, 0.9])
        
        with col_chk:
            chk_resumen = st.checkbox("Imprimir resumen (solo totales)", key="chk_resumen")
            
        with col_sel:
            opciones_agrupacion = sorted(["Destajista", "Estado de Pago", "Lote", "Manzana", "Partida", "Prototipo"])
            if chk_resumen:
                st.selectbox("Agrupar totales por:", options=opciones_agrupacion, key="sel_agrupacion", label_visibility="collapsed")
 
    df_rep_filtrado = df_base_rep.copy()
    
    if st.session_state.rep_sel_proto: 
        df_rep_filtrado = df_rep_filtrado[df_rep_filtrado['Prototipo'].isin(st.session_state.rep_sel_proto)]
    if st.session_state.rep_sel_manzana: 
        df_rep_filtrado = df_rep_filtrado[df_rep_filtrado['Manzana'].isin(st.session_state.rep_sel_manzana)]
    if st.session_state.rep_sel_lotes: 
        df_rep_filtrado = df_rep_filtrado[df_rep_filtrado['Lote'].astype(str).isin(st.session_state.rep_sel_lotes)]
    if st.session_state.rep_sel_concepto: 
        df_rep_filtrado = df_rep_filtrado[df_rep_filtrado['Concepto_Limpio'].isin(st.session_state.rep_sel_concepto)]
    if st.session_state.rep_sel_dest: 
        df_rep_filtrado = df_rep_filtrado[df_rep_filtrado['Destajista'].isin(st.session_state.rep_sel_dest)]
    
    # --- NUEVO: Lógica de filtrado con checkboxes ---
    if chk_pagado and not chk_por_pagar:
        df_rep_filtrado = df_rep_filtrado[df_rep_filtrado['Fecha pago'] != '']
        estado_filtro_str = "Pagado"
    elif chk_por_pagar and not chk_pagado:
        df_rep_filtrado = df_rep_filtrado[df_rep_filtrado['Fecha pago'] == '']
        estado_filtro_str = "Pendiente (Por Pagar)"
    elif not chk_pagado and not chk_por_pagar:
        df_rep_filtrado = df_rep_filtrado.iloc[0:0] # Tabla vacía si el usuario desmarca ambos
        estado_filtro_str = "Ninguno"
    else:
        estado_filtro_str = "Todos"
    # ------------------------------------------------
            
    if rango and len(rango) == 2:
        meses_regex = {
            r'/Ene/': '/01/', r'/Feb/': '/02/', r'/Mar/': '/03/', r'/Abr/': '/04/', 
            r'/May/': '/05/', r'/Jun/': '/06/', r'/Jul/': '/07/', r'/Ago/': '/08/', 
            r'/Sep/': '/09/', r'/Oct/': '/10/', r'/Nov/': '/11/', r'/Dic/': '/12/'
        }
        df_rep_filtrado['Fecha_Parse'] = df_rep_filtrado['Fecha pago'].replace(meses_regex, regex=True)
        df_rep_filtrado['Fecha_Obj_Temp'] = pd.to_datetime(df_rep_filtrado['Fecha_Parse'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date
        df_rep_filtrado = df_rep_filtrado[(df_rep_filtrado['Fecha_Obj_Temp'] >= rango[0]) & (df_rep_filtrado['Fecha_Obj_Temp'] <= rango[1])]
        df_rep_filtrado = df_rep_filtrado.drop(columns=['Fecha_Obj_Temp', 'Fecha_Parse'])
        
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"Partidas que se incluirán en el documento: `{len(df_rep_filtrado)}` partidas.")
    st.markdown("<br>", unsafe_allow_html=True)

    if df_rep_filtrado.empty:
        st.warning("No existen registros bajo los filtros seleccionados para generar el documento.")
    else:
        # --- NUEVA LÓGICA DE RENDIMIENTO ---
        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
        st.info("💡 **Tip de rendimiento:** Mueve tus filtros libremente arriba. El contador de partidas se actualizará en tiempo real. Cuando estés listo para imprimir, activa la casilla de abajo.")
        
        generar_pdf = st.toggle("⚙️ Construir documento PDF con estos filtros")
        
        if generar_pdf:
            with st.spinner("⏳ Compilando el PDF, por favor espera un momento..."):
                pdf = FPDF(orientation='P', unit='mm', format='Letter')
                pdf.add_page()
                        
                pdf.set_font("Arial", 'B', 14)
                pdf.set_text_color(30, 58, 138) 
                pdf.cell(195, 8, txt="REPORTES DE ESTIMACIONES Y DESTAJOS", ln=True, align='C')
                
                # Inyección superior del nombre de la obra en el PDF
                pdf.set_font("Arial", 'B', 10)
                pdf.set_text_color(75, 85, 99)
                pdf.cell(195, 5, txt=f"OBRA: {str(st.session_state.obra_actual).upper()}", ln=True, align='C')
                
                pdf.set_font("Arial", 'I', 9)
                pdf.set_text_color(108, 117, 125)
                tz_mx = ZoneInfo("America/Mexico_City")
                fecha_impresion = datetime.now(tz_mx).strftime("%d/%m/%Y %H:%M:%S")
                pdf.cell(195, 5, txt=f"Generado el: {fecha_impresion} (Zona Horaria México)", ln=True, align='C')
                pdf.ln(5)
                
                pdf.set_font("Arial", 'B', 9)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(195, 5, txt="Filtros del Reporte:", ln=True)
                pdf.set_font("Arial", '', 9)
                
                txt_proto = ", ".join(st.session_state.rep_sel_proto) if st.session_state.rep_sel_proto else "Todos"
                txt_mz = ", ".join(st.session_state.rep_sel_manzana) if st.session_state.rep_sel_manzana else "Todas"
                txt_dest = ", ".join(st.session_state.rep_sel_dest) if st.session_state.rep_sel_dest else "Todos"

                tipo_reporte_txt = f" | MODO: RESUMEN POR {str(st.session_state.get('sel_agrupacion', 'DESTAJISTA')).upper()}" if chk_resumen else ""
                criterios = f"Proto: {txt_proto} | Mz: {txt_mz} | Dest: {txt_dest} | Est: {estado_filtro_str}{tipo_reporte_txt}"
                
                if rango and len(rango) == 2:
                    criterios += f" | Rango: {rango[0].strftime('%d/%m/%Y')} al {rango[1].strftime('%d/%m/%Y')}"
                    
                pdf.cell(195, 5, txt=criterios[:115], ln=True)
                pdf.ln(4)

                if chk_resumen:
                    mapa_columnas = {
                        "Destajista": "Destajista",
                        "Estado de Pago": "Estado_Pago_Temp",
                        "Lote": "Lote",
                        "Manzana": "Manzana",
                        "Partida": "Partida",
                        "Prototipo": "Prototipo"
                    }
                    col_agrupar = mapa_columnas.get(st.session_state.get("sel_agrupacion", "Destajista"), "Destajista")

                    if col_agrupar == "Estado_Pago_Temp":
                        df_rep_filtrado["Estado_Pago_Temp"] = df_rep_filtrado["Fecha pago"].apply(lambda x: "Pendiente" if str(x).strip() == "" else "Pagado")

                    df_rep_filtrado['Costo_Num'] = pd.to_numeric(df_rep_filtrado['Costo'], errors='coerce').fillna(0)
                    df_rep_filtrado['% Adicional_Num'] = pd.to_numeric(df_rep_filtrado['% Adicional'], errors='coerce').fillna(0)
                    df_rep_filtrado['% Retención_Num'] = pd.to_numeric(df_rep_filtrado['% Retención'], errors='coerce').fillna(0)
                    
                    df_rep_filtrado['Monto_Neto_Reporte'] = df_rep_filtrado['Costo_Num'] + (df_rep_filtrado['Costo_Num'] * df_rep_filtrado['% Adicional_Num']) - (df_rep_filtrado['Costo_Num'] * df_rep_filtrado['% Retención_Num'])
                    
                    df_resumen = df_rep_filtrado.groupby(col_agrupar)['Monto_Neto_Reporte'].sum().reset_index()
                    df_resumen.columns = [col_agrupar, 'Costo'] 

                    pdf.set_font("Arial", 'B', 10)
                    pdf.set_fill_color(30, 58, 138) 
                    pdf.set_text_color(255, 255, 255) 
                    
                    w_col1, w_col2 = 145, 50
                    pdf.cell(w_col1, 8, txt=st.session_state.get("sel_agrupacion", "Destajista"), border=1, align='C', fill=True)
                    pdf.cell(w_col2, 8, txt="Total Acumulado", border=1, align='C', fill=True)
                    pdf.ln(8)

                    pdf.set_font("Arial", '', 9)
                    pdf.set_text_color(0, 0, 0)
                    total_general = 0
                    fondo_cebra = False

                    for _, row in df_resumen.iterrows():
                        valor_txt = str(row[col_agrupar]).strip()
                        if valor_txt == "" or valor_txt.lower() in ['nan', 'none', '<na>']:
                            continue
                        
                        if fondo_cebra:
                            pdf.set_fill_color(245, 247, 250) 
                        else:
                            pdf.set_fill_color(255, 255, 255)
                            
                        costo_fila = float(row['Costo'])

                        if chk_por_pagar and not chk_pagado:
                            costo_fila = -abs(costo_fila)

                        pdf.cell(w_col1, 7, txt=valor_txt[:80], border=1, align='L', fill=True)
                        pdf.cell(w_col2, 7, txt=f"${costo_fila:,.2f}", border=1, align='R', fill=True)
                        pdf.ln(7)
                        
                        total_general += costo_fila
                        fondo_cebra = not fondo_cebra

                    pdf.set_font("Arial", 'B', 10)
                    pdf.set_fill_color(230, 235, 245)
                    pdf.cell(w_col1, 8, txt=f"GRAN TOTAL ({str(st.session_state.get('sel_agrupacion', 'DESTAJISTA')).upper()}) ", border=1, align='R', fill=True)
                    pdf.cell(w_col2, 8, txt=f"${total_general:,.2f}", border=1, align='R', fill=True)

                else:
                    w_lote, w_mz, w_proto, w_partida, w_dest, w_costo = 15, 15, 25, 60, 50, 30
                    pdf.set_font("Arial", 'B', 10)
                    pdf.set_fill_color(30, 58, 138) 
                    pdf.set_text_color(255, 255, 255) 
                    
                    pdf.cell(w_lote, 8, txt="Lote", border=1, align='C', fill=True)
                    pdf.cell(w_mz, 8, txt="Mz", border=1, align='C', fill=True)
                    pdf.cell(w_proto, 8, txt="Prototipo", border=1, align='C', fill=True)
                    pdf.cell(w_partida, 8, txt="Partida / Concepto", border=1, align='L', fill=True)
                    pdf.cell(w_dest, 8, txt="Destajista", border=1, align='L', fill=True)
                    pdf.cell(w_costo, 8, txt="Costo", border=1, align='R', fill=True)
                    pdf.ln(8)
                    
                    pdf.set_font("Arial", '', 9)
                    pdf.set_text_color(0, 0, 0)
                    total_acumulado = 0
                    fondo_cebra = False
                    
                    for _, row in df_rep_filtrado.iterrows():
                        if fondo_cebra:
                            pdf.set_fill_color(245, 247, 250) 
                        else:
                            pdf.set_fill_color(255, 255, 255)
                            
                        dest_txt = str(row['Destajista']).strip() if str(row['Destajista']).strip() else "Sin Asignar"
                        proto_txt = str(row['Prototipo']).replace("Prototipo ", "")
                        
                        pdf.cell(w_lote, 7, txt=str(row['Lote'])[:6], border=1, align='C', fill=True)
                        pdf.cell(w_mz, 7, txt=str(row['Manzana'])[:6], border=1, align='C', fill=True)
                        pdf.cell(w_proto, 7, txt=proto_txt[:12], border=1, align='C', fill=True)
                        pdf.cell(w_partida, 7, txt=str(row['Partida'])[:33], border=1, align='L', fill=True)
                        c_neto = float(row['Costo']) + (float(row['Costo']) * (float(row['% Adicional']) if row['% Adicional'] else 0)) - (float(row['Costo']) * (float(row['% Retención']) if row['% Retención'] else 0))
                        
                        if chk_por_pagar and not chk_pagado:
                            c_neto = -abs(c_neto)
                        pdf.cell(w_dest, 7, txt=dest_txt[:26], border=1, align='L', fill=True)
                        pdf.cell(w_costo, 7, txt=f"${c_neto:,.2f}", border=1, align='R', fill=True)
                        pdf.ln(7)
                        
                        total_acumulado += c_neto   
                        fondo_cebra = not fondo_cebra
                    
                    pdf.set_font("Arial", 'B', 10)
                    pdf.set_fill_color(230, 235, 245)
                    pdf.cell(165, 8, txt="TOTAL GENERAL ESTIMADO FILTRADO  ", border=1, align='R', fill=True)
                    pdf.cell(w_costo, 8, txt=f"${total_acumulado:,.2f}", border=1, align='R', fill=True)
                
                pdf_bytes = bytes(pdf.output())

                st.markdown(
                    """
                    <style>
                    div[data-testid="stColumn"]:nth-of-type(3) button {
                        background-color: #dc3545 !important;
                        color: white !important;
                        border-radius: 5px;
                        border: none;
                    }
                    div[data-testid="stColumn"]:nth-of-type(3) button:hover {
                        background-color: #bd2130 !important;
                        color: white !important;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )

                c_vacia1, c_vacia2, c_boton = st.columns([3, 1, 1.2])
                with c_boton:
                    st.download_button(
                        label="📥 Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"Reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
        
if st.sidebar.button("📄 Reportes"):
    dialogo_reportes()

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state.usuario = None
    st.rerun()

@st.dialog("➕ Añadir Nueva Partida Adicional", width="large")
def dialogo_nueva_partida():
    st.markdown("### 📝 Registrar nuevo concepto")
    st.write("El sistema inyectará la partida exactamente debajo de la última fila del lote correspondiente.")
    
    lotes_unicos = list(set([str(x).strip() for x in st.session_state.df['Lote'].unique() if str(x).strip()]))
    list_lotes = sorted(lotes_unicos, key=natural_sort_key)
    
    c1, c2 = st.columns(2)
    with c1:
        lotes_sel = st.multiselect("Lote(s) *", options=list_lotes, help="Obligatorio. Se creará una fila por cada lote elegido.")
        dest_sel = st.selectbox("Destajista", options=[""] + [d for d in LISTA_DESTAJISTAS if d.strip()])
        pct_adicional_sel = st.selectbox("% Adicional", options=["0%", "10%"])
    with c2:
        partida_txt = st.text_input("Concepto / Partida *", help="Obligatorio.")
        costo_txt = st.text_input("Costo unitario ($) *", placeholder="Ej. 1,500.00", help="Obligatorio. Puedes usar comas.")
        pct_retencion_sel = st.selectbox("% Retención", options=["0%", "5%"])
        
    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
    pagar_ahora = st.radio("💳 ¿Deseas marcar y pagar estas partidas en este momento?", 
                           ["No, solo agregarlas a la tabla", "Sí, pagarlas ahora mismo"], horizontal=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    col_canc, col_asig = st.columns([1, 1])
    
    if col_canc.button("❌ Cancelar", use_container_width=True):
        st.rerun()
        
    if col_asig.button("✅ Asignar y Guardar", type="primary", use_container_width=True):
        if not lotes_sel or not partida_txt.strip() or not costo_txt.strip():
            st.error("⚠️ Por favor, llena los campos obligatorios: Lote(s), Partida y Costo.")
            return
            
        costo_limpio = costo_txt.replace("$", "").replace(",", "").replace(" ", "").strip()
        try:
            costo_float = float(costo_limpio)
        except ValueError:
            st.error("⚠️ El costo introducido no es un número válido. Verifica el formato.")
            return
            
        partida_final = f"{partida_txt.strip()} (*)"
        
        # Procesar porcentajes y fondo de garantía
        pct_ad_float = 0.10 if pct_adicional_sel == "10%" else 0.0
        pct_ret_float = 0.05 if pct_retencion_sel == "5%" else 0.0
        monto_ret_float = costo_float * pct_ret_float if pct_ret_float > 0 else 0.0
        estatus_ret_str = "Retenido" if pct_ret_float > 0 else ""
        
        if pagar_ahora == "Sí, pagarlas ahora mismo":
            pagar_bool = True
            tz_mx = ZoneInfo("America/Mexico_City")
            tiempo_actual = datetime.now(tz_mx)
            meses_3_letras = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
            ahora = f"{tiempo_actual.strftime('%d')}/{meses_3_letras[tiempo_actual.month]}/{tiempo_actual.strftime('%Y')} {tiempo_actual.strftime('%H:%M:%S')}"
            usr = st.session_state.usuario
        else:
            pagar_bool = False
            ahora = ""
            usr = ""
            
        df_temp = st.session_state.df.copy()
        
        # --- NUEVO: Alineación y ordenamiento estricto previo con ID_DB ---
        df_temp['ID_DB_Num'] = pd.to_numeric(df_temp['ID_DB'], errors='coerce')
        df_temp['Lote_Num'] = pd.to_numeric(df_temp['Lote'], errors='coerce').fillna(9999)
        df_temp['Partida_Limpia'] = df_temp['Partida'].apply(limpiar_texto_partida)
        df_temp['Orden_Excel'] = df_temp['Partida_Limpia'].apply(
            lambda x: ORDEN_PARTIDAS_MAESTRO.index(x) if x in ORDEN_PARTIDAS_MAESTRO else 99999
        )
        
        # Ordenamos usando el ID_DB_Num como desempate (las más antiguas arriba, las nuevas al final)
        df_temp = df_temp.sort_values(by=['Lote_Num', 'Prototipo', 'Orden_Excel', 'ID_DB_Num'], na_position='last').reset_index(drop=True)
        df_temp = df_temp.drop(columns=['Lote_Num', 'Partida_Limpia', 'Orden_Excel', 'ID_DB_Num'])
        # -------------------------------------------------------
        
        for lote in lotes_sel:
            datos_lote_existente = df_temp[df_temp['Lote'].astype(str).str.strip() == str(lote).strip()]
            
            if not datos_lote_existente.empty:
                lote_original = datos_lote_existente['Lote'].iloc[0]
                mz_original = datos_lote_existente['Manzana'].iloc[0]
                pr_original = datos_lote_existente['Prototipo'].iloc[0]
                idx_insert = datos_lote_existente.index.max() + 1
            else:
                lote_original = lote
                mz_original = ""
                pr_original = ""
                idx_insert = len(df_temp)

            nueva_fila = {
                'ID_DB': None,
                'Lote': lote_original,
                'Manzana': mz_original,
                'Prototipo': pr_original,
                'Partida': partida_final,
                'Costo': costo_float,
                'Destajista': dest_sel,
                '% Adicional': pct_ad_float,  
                '% Retención': pct_ret_float,  
                'Monto Retenido': monto_ret_float,
                'Estatus Retención': estatus_ret_str,
                'Fecha Liberación': "",
                'Usuario Liberó': "",
                'Pagar': pagar_bool,
                'Fecha pago': ahora,
                'Usuario': usr
            }
            
            df_arriba = df_temp.iloc[:idx_insert]
            df_abajo = df_temp.iloc[idx_insert:]
            df_temp = pd.concat([df_arriba, pd.DataFrame([nueva_fila]), df_abajo]).reset_index(drop=True)
            
        df_envio = df_temp.copy()
        if 'Concepto_Limpio' in df_envio.columns:
            df_envio = df_envio.drop(columns=['Concepto_Limpio'])
            
        df_envio['Fecha pago'] = df_envio['Fecha pago'].apply(lambda x: f"'{x}" if str(x).strip() != '' else '')
        
        with st.spinner("Inyectando partida en el lote correspondiente y sincronizando con Supabase..."):
            actualizar_datos_gsheet(df_envio)
            st.session_state.df = obtener_datos_gsheet()
            
        st.session_state.df_original = st.session_state.df.copy()
        st.session_state.grid_key += 1
        st.success("¡Partida(s) inyectada(s) exactamente al final de cada grupo!")
        st.rerun()

# --- TABLA DE RESUMEN DE PROTOTIPOS EN EL PANEL LATERAL (INFERIOR) ---
if not st.session_state.df.empty:
    df_side = st.session_state.df.copy()
    df_side['Costo'] = pd.to_numeric(df_side['Costo'], errors='coerce').fillna(0)
    
    df_resumen_proto = df_side.groupby('Prototipo').agg(
        Cantidad=('Lote', 'nunique'),
        Costo=('Costo', 'sum')
    ).reset_index()
    
    df_resumen_proto['sort_key'] = df_resumen_proto['Prototipo'].apply(sort_prototipos)
    df_resumen_proto = df_resumen_proto.sort_values(by='sort_key').drop(columns=['sort_key'])
    
    total_cantidad_protos = df_resumen_proto['Cantidad'].sum()
    total_general_protos = df_resumen_proto['Costo'].sum()
    
    df_mostrar_sidebar = df_resumen_proto.copy()
    df_mostrar_sidebar['Total'] = df_mostrar_sidebar['Costo'].apply(lambda x: f"${x:,.2f}")
    df_mostrar_sidebar = df_mostrar_sidebar[['Prototipo', 'Cantidad', 'Total']]
    
    fila_total = pd.DataFrame([{
        'Prototipo': 'TOTAL', 
        'Cantidad': total_cantidad_protos, 
        'Total': f"${total_general_protos:,.2f}"
    }])
    df_mostrar_sidebar = pd.concat([df_mostrar_sidebar, fila_total], ignore_index=True)
    
    st.sidebar.markdown("<br><hr>", unsafe_allow_html=True)
    st.sidebar.markdown("##### 📊 Resumen por Prototipo")
    st.sidebar.dataframe(df_mostrar_sidebar, hide_index=True, use_container_width=True)

# =========================================================================
# PESTAÑA 1: REGISTRO DE DESTAJOS
# =========================================================================
if menu == "Registro de Destajos":
    mostrar_cabecera_con_logo("📝 Control de Pagos Destajos")
    
    df_actual = st.session_state.df
    
    espacio_kpi = st.empty() 
    espacio_filtros = st.container() 

    with espacio_filtros:
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

        # --- CÓDIGO PARA FILTROS EN CASCADA / DEPENDIENTES ---
        df_p = df_actual.copy()
        df_p['Partida_Num'] = df_p['Partida'].apply(extraer_numero_partida)
        df_p['Concepto_Limpio'] = df_p['Partida'].apply(limpiar_texto_partida)

        # 1. Opciones de Prototipo
        df_proto_opts = df_p.copy()
        if st.session_state.sel_manzana != "Todos": df_proto_opts = df_proto_opts[df_proto_opts['Manzana'] == st.session_state.sel_manzana]
        if st.session_state.sel_lotes: df_proto_opts = df_proto_opts[df_proto_opts['Lote'].astype(str).isin(st.session_state.sel_lotes)]
        if st.session_state.sel_concepto: df_proto_opts = df_proto_opts[df_proto_opts['Concepto_Limpio'].isin(st.session_state.sel_concepto)]
        if st.session_state.sel_dest != "Todos": df_proto_opts = df_proto_opts[df_proto_opts['Destajista'] == st.session_state.sel_dest]
        if st.session_state.sel_estado != "Todos":
            if st.session_state.sel_estado == "Pagado": df_proto_opts = df_proto_opts[df_proto_opts['Fecha pago'] != '']
            else: df_proto_opts = df_proto_opts[df_proto_opts['Fecha pago'] == '']
        list_prototipos = sorted(df_proto_opts['Prototipo'].unique().tolist(), key=sort_prototipos)

        # 2. Opciones de Manzana
        df_mz_opts = df_p.copy()
        if st.session_state.sel_proto != "Todos": df_mz_opts = df_mz_opts[df_mz_opts['Prototipo'] == st.session_state.sel_proto]
        if st.session_state.sel_lotes: df_mz_opts = df_mz_opts[df_mz_opts['Lote'].astype(str).isin(st.session_state.sel_lotes)]
        if st.session_state.sel_concepto: df_mz_opts = df_mz_opts[df_mz_opts['Concepto_Limpio'].isin(st.session_state.sel_concepto)]
        if st.session_state.sel_dest != "Todos": df_mz_opts = df_mz_opts[df_mz_opts['Destajista'] == st.session_state.sel_dest]
        if st.session_state.sel_estado != "Todos":
            if st.session_state.sel_estado == "Pagado": df_mz_opts = df_mz_opts[df_mz_opts['Fecha pago'] != '']
            else: df_mz_opts = df_mz_opts[df_mz_opts['Fecha pago'] == '']
        list_manzanas = sorted([x for x in df_mz_opts['Manzana'].unique().tolist() if str(x).strip()], key=natural_sort_key)

        # 3. Opciones de Lotes
        df_lote_opts = df_p.copy()
        if st.session_state.sel_proto != "Todos": df_lote_opts = df_lote_opts[df_lote_opts['Prototipo'] == st.session_state.sel_proto]
        if st.session_state.sel_manzana != "Todos": df_lote_opts = df_lote_opts[df_lote_opts['Manzana'] == st.session_state.sel_manzana]
        if st.session_state.sel_concepto: df_lote_opts = df_lote_opts[df_lote_opts['Concepto_Limpio'].isin(st.session_state.sel_concepto)]
        if st.session_state.sel_dest != "Todos": df_lote_opts = df_lote_opts[df_lote_opts['Destajista'] == st.session_state.sel_dest]
        if st.session_state.sel_estado != "Todos":
            if st.session_state.sel_estado == "Pagado": df_lote_opts = df_lote_opts[df_lote_opts['Fecha pago'] != '']
            else: df_lote_opts = df_lote_opts[df_lote_opts['Fecha pago'] == '']
        list_lotes = sorted([str(x) for x in df_lote_opts['Lote'].unique().tolist() if str(x).strip()], key=natural_sort_key)

        # 4. Opciones de Concepto / Partida (MÁGIA DE ORDENAMIENTO OCULTO)
        # 4. Opciones de Concepto / Partida (ORDEN ESTRICTO DEL EXCEL)
        df_concepto_opts = df_p.copy()
        if st.session_state.sel_proto != "Todos": df_concepto_opts = df_concepto_opts[df_concepto_opts['Prototipo'] == st.session_state.sel_proto]
        if st.session_state.sel_manzana != "Todos": df_concepto_opts = df_concepto_opts[df_concepto_opts['Manzana'] == st.session_state.sel_manzana]
        if st.session_state.sel_lotes: df_concepto_opts = df_concepto_opts[df_concepto_opts['Lote'].astype(str).isin(st.session_state.sel_lotes)]
        if st.session_state.sel_dest != "Todos": df_concepto_opts = df_concepto_opts[df_concepto_opts['Destajista'] == st.session_state.sel_dest]
        if st.session_state.sel_estado != "Todos":
            if st.session_state.sel_estado == "Pagado": df_concepto_opts = df_concepto_opts[df_concepto_opts['Fecha pago'] != '']
            else: df_concepto_opts = df_concepto_opts[df_concepto_opts['Fecha pago'] == '']
        
        # Filtramos, limpiamos y obligamos a que se ordenen usando la Lista Maestra
        conceptos_presentes = [str(c).strip() for c in df_concepto_opts['Concepto_Limpio'].unique() if str(c).strip()]
        list_conceptos = sorted(
            conceptos_presentes, 
            key=lambda x: ORDEN_PARTIDAS_MAESTRO.index(x) if x in ORDEN_PARTIDAS_MAESTRO else 99999
        )

        # 5. Opciones de Destajista
        df_dest_opts = df_p.copy()
        if st.session_state.sel_proto != "Todos": df_dest_opts = df_dest_opts[df_dest_opts['Prototipo'] == st.session_state.sel_proto]
        if st.session_state.sel_manzana != "Todos": df_dest_opts = df_dest_opts[df_dest_opts['Manzana'] == st.session_state.sel_manzana]
        if st.session_state.sel_lotes: df_dest_opts = df_dest_opts[df_dest_opts['Lote'].astype(str).isin(st.session_state.sel_lotes)]
        if st.session_state.sel_concepto: df_dest_opts = df_dest_opts[df_dest_opts['Concepto_Limpio'].isin(st.session_state.sel_concepto)]
        if st.session_state.sel_estado != "Todos":
            if st.session_state.sel_estado == "Pagado": df_dest_opts = df_dest_opts[df_dest_opts['Fecha pago'] != '']
            else: df_dest_opts = df_dest_opts[df_dest_opts['Fecha pago'] == '']
        list_destajistas_filtro = ["Todos"] + sorted([str(d) for d in df_dest_opts['Destajista'].unique() if str(d).strip()], key=natural_sort_key)
        
        df_filtrado = df_actual.copy()
        df_filtrado['Concepto_Limpio'] = df_filtrado['Partida'].apply(limpiar_texto_partida)
       

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

    df_filtrado = df_actual.copy()
    df_filtrado['Concepto_Limpio'] = df_filtrado['Partida'].apply(lambda x: re.sub(r'^\d+[\s\.\-]*', '', str(x)).strip())
    if st.session_state.sel_proto != "Todos": df_filtrado = df_filtrado[df_filtrado['Prototipo'] == st.session_state.sel_proto]
    if st.session_state.sel_manzana != "Todos": df_filtrado = df_filtrado[df_filtrado['Manzana'] == st.session_state.sel_manzana]
    if st.session_state.sel_lotes: df_filtrado = df_filtrado[df_filtrado['Lote'].astype(str).isin(st.session_state.sel_lotes)]
    if st.session_state.sel_concepto: df_filtrado = df_filtrado[df_filtrado['Concepto_Limpio'].isin(st.session_state.sel_concepto)]
    if st.session_state.sel_dest != "Todos": df_filtrado = df_filtrado[df_filtrado['Destajista'] == st.session_state.sel_dest]
    
    if st.session_state.sel_estado != "Todos":
        if st.session_state.sel_estado == "Pagado": df_filtrado = df_filtrado[df_filtrado['Fecha pago'] != '']
        else: df_filtrado = df_filtrado[df_filtrado['Fecha pago'] == '']
            
    if st.session_state.sel_fecha and len(st.session_state.sel_fecha) == 2:
        meses_regex = {
            r'/Ene/': '/01/', r'/Feb/': '/02/', r'/Mar/': '/03/', r'/Abr/': '/04/', 
            r'/May/': '/05/', r'/Jun/': '/06/', r'/Jul/': '/07/', r'/Ago/': '/08/', 
            r'/Sep/': '/09/', r'/Oct/': '/10/', r'/Nov/': '/11/', r'/Dic/': '/12/'
        }
        df_filtrado['Fecha_Parse'] = df_filtrado['Fecha pago'].replace(meses_regex, regex=True)
        df_filtrado['Fecha_Obj_Temp'] = pd.to_datetime(df_filtrado['Fecha_Parse'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date
        df_filtrado = df_filtrado[(df_filtrado['Fecha_Obj_Temp'] >= st.session_state.sel_fecha[0]) & (df_filtrado['Fecha_Obj_Temp'] <= st.session_state.sel_fecha[1])]
        df_filtrado = df_filtrado.drop(columns=['Fecha_Obj_Temp', 'Fecha_Parse'])

    costo_total_filtrado = df_filtrado['Costo'].sum()
    pagado_filtrado = df_filtrado.loc[df_filtrado['Fecha pago'] != '', 'Costo'].sum()
    pendiente_filtrado = costo_total_filtrado - pagado_filtrado
    
    espacio_kpi.markdown(f"""
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
        st.session_state.reload_trigger = True
        st.rerun()
        
    if b_col2.button("🔲 Seleccionar Ninguno", use_container_width=True):
        indices_pendientes = df_filtrado[df_filtrado['Fecha pago'] == ''].index
        st.session_state.df.loc[indices_pendientes, 'Pagar'] = False
        st.session_state.reload_trigger = True
        st.rerun()

    # --- 1. Asignación Destajista ---
    destajista_masivo = b_col3.selectbox("Destajista M.", ["Seleccionar..."] + LISTA_DESTAJISTAS, label_visibility="collapsed")
    if b_col3.button("Asignar Destajista Masivo", use_container_width=True):
        if destajista_masivo != "Seleccionar...":
            st.session_state.df.loc[df_filtrado.index, 'Destajista'] = destajista_masivo
            st.session_state.reload_trigger = True
            st.success("Destajista asignado masivamente.")
            st.rerun()

    # --- 2. Asignación % Adicional ---
    pct_adicional_masivo = b_col4.selectbox("% Adic M.", ["Seleccionar...", "0%", "10%"], label_visibility="collapsed")
    if b_col4.button("Asignación masiva % Adicional", use_container_width=True):
        if pct_adicional_masivo != "Seleccionar...":
            val = 0.10 if pct_adicional_masivo == "10%" else 0.0
            st.session_state.df.loc[df_filtrado.index, '% Adicional'] = val
            st.session_state.reload_trigger = True
            st.success("% Adicional asignado masivamente.")
            st.rerun()

    # --- 3. Asignación % Retención ---
    pct_retencion_masiva = b_col5.selectbox("% Ret M.", ["Seleccionar...", "0%", "5%"], label_visibility="collapsed")
    if b_col5.button("Asignación masiva % Retención", use_container_width=True):
        if pct_retencion_masiva != "Seleccionar...":
            val = 0.05 if pct_retencion_masiva == "5%" else 0.0
            st.session_state.df.loc[df_filtrado.index, '% Retención'] = val
            st.session_state.reload_trigger = True
            st.success("% Retención asignado masivamente.")
            st.rerun()

    ph_indicador_suma = st.empty() # Contenedor para reubicar la Suma a Pagar

    ph_label_azul = st.empty()
    st.markdown("<hr style='margin:5px 0 5px 0;'>", unsafe_allow_html=True)
    
    c_btn_add, c_btn_space = st.columns([2, 8])
    with c_btn_add:
        if st.button("➕ Añadir nueva partida", type="primary", use_container_width=True):
            dialogo_nueva_partida()
    st.markdown("<hr style='margin:5px 0 10px 0;'>", unsafe_allow_html=True)

    df_filtrado_grid = df_filtrado.copy()
    df_filtrado_grid['_original_index'] = df_filtrado_grid.index
    
    df_filtrado_grid['Lote_Num'] = pd.to_numeric(df_filtrado_grid['Lote'], errors='coerce').fillna(9999)
    # TRUCO VISUAL: Limpiamos la partida en pantalla para quitar el número 
    df_filtrado_grid['Partida'] = df_filtrado_grid['Partida'].apply(limpiar_texto_partida)
    
    # Creamos columna de orden guiada ESTRICTAMENTE por tu Excel
    df_filtrado_grid['Orden_Excel'] = df_filtrado_grid['Partida'].apply(
        lambda x: ORDEN_PARTIDAS_MAESTRO.index(x) if x in ORDEN_PARTIDAS_MAESTRO else 99999
    )
    
    # Convertimos ID_DB a numérico para desempate estable
    df_filtrado_grid['ID_DB_Num'] = pd.to_numeric(df_filtrado_grid['ID_DB'], errors='coerce')
    
    # ORDENAMOS LA TABLA respetando lotes, la lista maestra y finalmente el ID de creación
    df_filtrado_grid = df_filtrado_grid.sort_values(by=['Lote_Num', 'Prototipo', 'Orden_Excel', 'ID_DB_Num', '_original_index'], na_position='last')
    df_filtrado_grid = df_filtrado_grid.drop(columns=['Lote_Num', 'Orden_Excel', 'ID_DB_Num'])
    # -------------------------------------------------------------

    
    
    for c_ad in ['% Adicional', '% Retención', 'Monto Retenido', 'Estatus Retención', 'Fecha Liberación', 'Usuario Liberó']:
        if c_ad not in df_filtrado_grid.columns:
            df_filtrado_grid[c_ad] = 0.0 if 'Monto' in c_ad or '%' in c_ad else ""
            
    df_filtrado_grid['% Ad_Temp'] = pd.to_numeric(df_filtrado_grid['% Adicional'], errors='coerce').fillna(0)
    df_filtrado_grid['% Ret_Temp'] = pd.to_numeric(df_filtrado_grid['% Retención'], errors='coerce').fillna(0)
    df_filtrado_grid['Costo_Temp'] = pd.to_numeric(df_filtrado_grid['Costo'], errors='coerce').fillna(0)
    
    df_filtrado_grid['Monto Neto'] = df_filtrado_grid['Costo_Temp'] + (df_filtrado_grid['Costo_Temp'] * df_filtrado_grid['% Ad_Temp']) - (df_filtrado_grid['Costo_Temp'] * df_filtrado_grid['% Ret_Temp'])
    
    if '% Adicional' not in df_filtrado_grid.columns: 
        df_filtrado_grid['% Adicional'] = 0.0
    if '% Retención' not in df_filtrado_grid.columns: 
        df_filtrado_grid['% Retención'] = 0.0
        
    df_filtrado_grid['% Ad_Temp'] = pd.to_numeric(df_filtrado_grid['% Adicional'], errors='coerce').fillna(0)
    df_filtrado_grid['% Ret_Temp'] = pd.to_numeric(df_filtrado_grid['% Retención'], errors='coerce').fillna(0)
    df_filtrado_grid['Costo_Temp'] = pd.to_numeric(df_filtrado_grid['Costo'], errors='coerce').fillna(0)
    
    df_filtrado_grid['Monto Neto'] = df_filtrado_grid['Costo_Temp'] + (df_filtrado_grid['Costo_Temp'] * df_filtrado_grid['% Ad_Temp']) - (df_filtrado_grid['Costo_Temp'] * df_filtrado_grid['% Ret_Temp'])
    
    gb = GridOptionsBuilder.from_dataframe(df_filtrado_grid[['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', '% Adicional', '% Retención', 'Monto Neto', 'Pagar', 'Fecha pago', 'Usuario', '_original_index', 'ID_DB']])
    gb.configure_default_column(sortable=False, filter=False, resizable=True)
    gb.configure_column("_original_index", hide=True)
    gb.configure_column("ID_DB", hide=True) # SE OCULTA LA CLAVE DE SUPABASE PERO VIAJA EN MEMORIA
    
    st.markdown(
        """
        <style>
        .ag-header-cell-label { justify-content: center !important; text-align: center !important; }
        .ag-header-cell-text { font-size: 20px !important; }
        .ag-cell, .ag-cell-value { font-size: 18px !important; display: flex !important; align-items: center !important; }
        .centrar-valor { justify-content: center !important; }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    gb.configure_column("Lote", type=["numericColumn","numberColumnFilter"], editable=False, filter=False, cellClass='centrar-valor', headerClass='ag-center-header', width=90)
    gb.configure_column("Manzana", editable=False, cellClass='centrar-valor', headerClass='ag-center-header', width=100)
    gb.configure_column("Prototipo", editable=False, cellClass='centrar-valor', headerClass='ag-center-header', width=110)
    gb.configure_column("Partida", editable=False, width=300) 
    gb.configure_column("Costo", editable=False, filter=False, valueFormatter="x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})", cellClass='centrar-valor', headerClass='ag-center-header', width=120)
    
    gb.configure_column("Destajista", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': LISTA_DESTAJISTAS}, singleClickEdit=True, width=200)
    gb.configure_column("% Adicional", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': [0, 0.10]}, valueFormatter="x ? (x*100)+'%' : '0%'", cellClass='centrar-valor', headerClass='ag-center-header', singleClickEdit=True, width=110)
    gb.configure_column("% Retención", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': [0, 0.05]}, valueFormatter="x ? (x*100)+'%' : '0%'", cellClass='centrar-valor', headerClass='ag-center-header', singleClickEdit=True, width=110)
    
    formula_neto = "Number(data.Costo) + (Number(data.Costo) * (Number(data['% Adicional']) || 0)) - (Number(data.Costo) * (Number(data['% Retención']) || 0))"
    gb.configure_column("Monto Neto", editable=False, valueGetter=formula_neto, valueFormatter="x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})", cellClass='centrar-valor', headerClass='ag-center-header', width=130)
    gb.configure_column("Pagar", editable=True, cellClass='centrar-valor', headerClass='ag-center-header', width=90)
    gb.configure_column("Fecha pago", editable=False, cellClass='centrar-valor', headerClass='ag-center-header', width=160)
    gb.configure_column("Usuario", editable=False, cellClass='centrar-valor', headerClass='ag-center-header', width=120)

    rowStyle = JsCode("""
    function(params) {
        let fp = params.data['Fecha pago'];
        let esta_pagado = (fp && fp.toString().trim() !== '' && fp !== 'nan' && fp !== 'null' && fp !== '<NA>');
        if (esta_pagado) { return { 'backgroundColor': '#e0e0e0', 'color': '#808080', 'pointerEvents': 'none', 'borderBottom': '1px solid #d3d3d3' }; }
        
        let style = { 'backgroundColor': '#0D0D0D', 'color': '#00FFFF', 'borderBottom': '1px solid #4a4a4a' };
        
        let check_pagar = params.data['Pagar'];
        if (check_pagar === true || check_pagar === 'true' || check_pagar === 1) {
            let dest = params.data['Destajista'];
            if (!dest || dest.trim() === '') { style['backgroundColor'] = '#4a0000'; }
        }
        return style;
    }
    """)
    gb.configure_grid_options(getRowStyle=rowStyle, rowHeight=30)
    
    grid_options = gb.build()

    mis_estilos = {
        ".ag-header-cell-text": {"font-size": "20px !important"}, 
        ".ag-header-cell-label": {"justify-content": "center !important"}, 
        ".ag-cell": {"font-size": "18px !important", "display": "flex", "align-items": "center"},
        ".ag-cell-value": {"font-size": "18px !important"},
        ".centrar-valor": {"justify-content": "center !important"}
    }

    # ====================================================
    # FORMULARIO ENCAPSULADOR (LA MAGIA CONTRA EL PARPADEO ESTÁ AQUÍ)
    # ====================================================
    with st.form(key=f"form_destajos_{st.session_state.grid_key}"):
        st.markdown(
            """
            <style>
            div[data-testid="stForm"] { 
                border: none !important; 
                padding: 0 !important; 
            }
            div[data-testid="stFormSubmitButton"] {
                display: flex !important;
                justify-content: flex-end !important;
                width: 100% !important;
                margin-top: -105px !important;
                margin-bottom: 15px !important;
                position: relative !important;
                z-index: 9999 !important;
            }
            div[data-testid="stFormSubmitButton"] button {
                width: 220px !important;
                background-color: #3B82F6 !important;
                color: white !important;
                border-radius: 8px !important;
                border: none !important;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
                height: 42px !important;
                font-weight: bold !important;
            }
            div[data-testid="stFormSubmitButton"] button:hover { 
                background-color: #2563EB !important; 
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        st.form_submit_button("🔄 Actualizar Totales", type="primary")
        
        response = AgGrid(
            df_filtrado_grid[['Lote', 'Manzana', 'Prototipo', 'Partida', 'Costo', 'Destajista', '% Adicional', '% Retención', 'Monto Neto', 'Pagar', 'Fecha pago', 'Usuario', '_original_index', 'ID_DB']].copy(),
            gridOptions=grid_options,
            key=f"grid_destajos_{st.session_state.grid_key}",
            reload_data=st.session_state.reload_trigger,
            enable_enterprise_modules=False,
            allow_unsafe_jscode=True,
            update_mode=GridUpdateMode.VALUE_CHANGED,  
            data_return_mode=DataReturnMode.AS_INPUT,  
            fit_columns_on_grid_load=False,
            theme='balham',
            height=800,
            custom_css=mis_estilos
        )
    st.session_state.reload_trigger = False

    if response['data'] is not None and not pd.DataFrame(response['data']).empty:
        df_grid = pd.DataFrame(response['data'])
        st.session_state.current_grid_state = df_grid 
        
        total_filas = len(df_grid)
        df_grid['Pagar_Bool'] = df_grid['Pagar'].astype(str).str.lower().isin(['true', '1'])
        df_grid['Fecha_Pago_Limpia'] = df_grid['Fecha pago'].fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>'], '')
        
        df_pagar_actual = df_grid[(df_grid['Pagar_Bool'] == True) & (df_grid['Fecha_Pago_Limpia'] == '')].copy()
        total_checked = len(df_pagar_actual)
        
        df_pagar_actual['C_Temp'] = pd.to_numeric(df_pagar_actual['Costo'], errors='coerce').fillna(0)
        df_pagar_actual['Ad_Temp'] = pd.to_numeric(df_pagar_actual['% Adicional'], errors='coerce').fillna(0)
        df_pagar_actual['Ret_Temp'] = pd.to_numeric(df_pagar_actual['% Retención'], errors='coerce').fillna(0)
        
        df_pagar_actual['Monto_Neto_Real'] = df_pagar_actual['C_Temp'] + (df_pagar_actual['C_Temp'] * df_pagar_actual['Ad_Temp']) - (df_pagar_actual['C_Temp'] * df_pagar_actual['Ret_Temp'])
        
        costo_seleccionado = df_pagar_actual['Monto_Neto_Real'].sum()

        # --- NUEVO: CÁLCULO DE PAGADO Y POR PAGAR EN PANTALLA ---
        df_grid['C_Temp_All'] = pd.to_numeric(df_grid['Costo'], errors='coerce').fillna(0)
        df_grid['Ad_Temp_All'] = pd.to_numeric(df_grid['% Adicional'], errors='coerce').fillna(0)
        df_grid['Ret_Temp_All'] = pd.to_numeric(df_grid['% Retención'], errors='coerce').fillna(0)
        df_grid['Monto_Neto_All'] = df_grid['C_Temp_All'] + (df_grid['C_Temp_All'] * df_grid['Ad_Temp_All']) - (df_grid['C_Temp_All'] * df_grid['Ret_Temp_All'])
        
        monto_pagado_pantalla = df_grid[df_grid['Fecha_Pago_Limpia'] != '']['Monto_Neto_All'].sum()
        monto_por_pagar_pantalla = df_grid[df_grid['Fecha_Pago_Limpia'] == '']['Monto_Neto_All'].sum()

        ph_indicador_suma.markdown(f"<div style='background-color:#F59E0B; color:black; padding:10px; border-radius:5px; text-align:center; font-weight:bold; font-size:18px;'>Suma a Pagar:<br>${costo_seleccionado:,.2f}</div>", unsafe_allow_html=True)
        
        ph_label_azul.markdown(f"""
        <div style='display: flex; justify-content: space-between; color: #3B82F6; font-weight: bold; background: transparent; font-size:14px; margin-bottom:5px; padding: 0 15px;'>
            <div>Partidas en pantalla: {total_filas} / Checkbox activados: {total_checked}</div>
            <div>✅ Pagado: ${monto_pagado_pantalla:,.2f} &nbsp;&nbsp;|&nbsp;&nbsp; ⏳ Por Pagar: ${monto_por_pagar_pantalla:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)        
    else:
        ph_indicador_suma.markdown(f"<div style='background-color:#F59E0B; color:black; padding:10px; border-radius:5px; text-align:center; font-weight:bold; font-size:18px;'>Suma a Pagar:<br>$0.00</div>", unsafe_allow_html=True)
        ph_label_azul.markdown(f"""
        <div style='display: flex; justify-content: space-between; color: #3B82F6; font-weight: bold; background: transparent; font-size:14px; margin-bottom:5px; padding: 0 15px;'>
            <div>Partidas en pantalla: 0 / Checkbox activados: 0</div>
            <div>✅ Pagado: $0.00 &nbsp;&nbsp;|&nbsp;&nbsp; ⏳ Por Pagar: $0.00</div>
        </div>
        """, unsafe_allow_html=True)
        

# =========================================================================
# NUEVA PESTAÑA: FONDO DE GARANTÍA (RETENCIONES)
# =========================================================================
elif menu == "Fondo de Garantía (Retenciones)":
    mostrar_cabecera_con_logo("🔒 Control de Fondos de Garantía y Retenciones", "Visualiza y libera los montos retenidos a los destajistas.")
    
    df_ret = st.session_state.df.copy()
    df_ret['_original_index'] = df_ret.index
    
    df_ret['Monto Retenido'] = pd.to_numeric(df_ret['Monto Retenido'], errors='coerce').fillna(0)
    df_ret_filtrado = df_ret[df_ret['Monto Retenido'] > 0].copy()

    # --- NUEVO: ORDENAMIENTO ESTRICTO CON DESEMPATE POR ID_DB PARA APILAR LAS NUEVAS AL FINAL ---
    if not df_ret_filtrado.empty:
        # 1. Preparamos las columnas numéricas para un orden perfecto
        df_ret_filtrado['Lote_Num'] = pd.to_numeric(df_ret_filtrado['Lote'], errors='coerce').fillna(9999)
        df_ret_filtrado['ID_DB_Num'] = pd.to_numeric(df_ret_filtrado['ID_DB'], errors='coerce')
        
        # 2. Limpiamos la partida para cruzarla con el índice del Excel Maestro
        df_ret_filtrado['Partida_Limpia'] = df_ret_filtrado['Partida'].apply(limpiar_texto_partida)
        df_ret_filtrado['Orden_Excel'] = df_ret_filtrado['Partida_Limpia'].apply(
            lambda x: ORDEN_PARTIDAS_MAESTRO.index(x) if x in ORDEN_PARTIDAS_MAESTRO else 99999
        )
        
        # 3. Aplicamos el ordenamiento multi-nivel exacto que usamos en la tabla principal
        df_ret_filtrado = df_ret_filtrado.sort_values(by=['Lote_Num', 'Prototipo', 'Orden_Excel', 'ID_DB_Num', '_original_index'], na_position='last')
        
        # 4. Eliminamos la "basura" temporal para no ensuciar el DataFrame
        df_ret_filtrado = df_ret_filtrado.drop(columns=['Lote_Num', 'ID_DB_Num', 'Partida_Limpia', 'Orden_Excel'])
    
    if df_ret_filtrado.empty:
        st.info("🎉 ¡Excelente! No existen fondos de garantía ni retenciones acumuladas en el sistema actualmente.")
    else:
        st.markdown("##### 💰 Acumulado de Retenciones por Contratista")
        kpi_cols = st.columns(3)
        idx_c = 0
        for dest_b in df_ret_filtrado['Destajista'].unique():
            if str(dest_b).strip():
                tot_ret = df_ret_filtrado[(df_ret_filtrado['Destajista'] == dest_b) & (df_ret_filtrado['Estatus Retención'] == "Retenido")]['Monto Retenido'].sum()
                tot_lib = df_ret_filtrado[(df_ret_filtrado['Destajista'] == dest_b) & (df_ret_filtrado['Estatus Retención'] == "Liberado")]['Monto Retenido'].sum()
                
                with kpi_cols[idx_c % 3]:
                    st.markdown(f"""
                    <div style='background-color:#1E293B; padding:12px; border-radius:8px; border-left: 5px solid #F59E0B; margin-bottom:10px;'>
                        <div style='font-size:14px; font-weight:bold; color:#F3F4F6;'>{dest_b}</div>
                        <div style='display:flex; justify-content:space-between; margin-top:5px;'>
                            <span style='font-size:12px; color:#FCA5A5;'>🔒 Retenido: ${tot_ret:,.2f}</span>
                            <span style='font-size:12px; color:#6EE7B7;'>🔓 Liberado: ${tot_lib:,.2f}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                idx_c += 1

        st.markdown("<br><hr>", unsafe_allow_html=True)
        st.markdown("### 📋 Listado Detallado de Retenciones")
        st.write("Para devolver un fondo de garantía, marca la casilla 'Liberar Fondo' y da clic en el botón guardar al final de la página.")
        
        df_ret_filtrado['Liberar_Check'] = df_ret_filtrado['Estatus Retención'].apply(lambda x: True if str(x).strip() == 'Liberado' else False)

        df_ret_filtrado['Fecha Liberación'] = df_ret_filtrado['Fecha Liberación'].fillna('').astype(str).replace(['nan', 'NaN', 'None', 'NaT', '<NA>'], '').str.strip()
        df_ret_filtrado['Usuario Liberó'] = df_ret_filtrado['Usuario Liberó'].fillna('').astype(str).replace(['nan', 'NaN', 'None', 'NaT', '<NA>'], '').str.strip()

        col_fecha, col_espacio, col_suma = st.columns([1.5, 0.5, 2])
        
        with col_fecha:
            st.markdown("##### 📅 Filtrar por Rango de Fechas")
            filtro_fecha_ret = st.date_input("Selecciona el período:", value=[], key="fecha_filtro_ret")
            ph_label_azul = st.empty() 

        ph_suma_naranja = col_suma.empty()

        if filtro_fecha_ret and len(filtro_fecha_ret) == 2:
            meses_regex = {
                r'/Ene/': '/01/', r'/Feb/': '/02/', r'/Mar/': '/03/', r'/Abr/': '/04/',
                r'/May/': '/05/', r'/Jun/': '/06/', r'/Jul/': '/07/', r'/Ago/': '/08/',
                r'/Sep/': '/09/', r'/Oct/': '/10/', r'/Nov/': '/11/', r'/Dic/': '/12/'
            }
            df_ret_filtrado['Fecha_Parse'] = df_ret_filtrado['Fecha Liberación'].replace(meses_regex, regex=True)
            df_ret_filtrado['Fecha_Obj_Temp'] = pd.to_datetime(df_ret_filtrado['Fecha_Parse'], format='%d/%m/%Y %H:%M:%S', errors='coerce').dt.date

            df_ret_filtrado = df_ret_filtrado[(df_ret_filtrado['Fecha_Obj_Temp'] >= filtro_fecha_ret[0]) & (df_ret_filtrado['Fecha_Obj_Temp'] <= filtro_fecha_ret[1])]
            df_ret_filtrado = df_ret_filtrado.drop(columns=['Fecha_Obj_Temp', 'Fecha_Parse'])

            total_filtrado_fechas = df_ret_filtrado['Monto Retenido'].sum()
            ph_label_azul.markdown(f"<div style='background-color:#3B82F6; color:white; padding:8px; border-radius:5px; text-align:center; font-weight:bold; font-size:14px; margin-top:5px;'>Total Monto Retenido: ${total_filtrado_fechas:,.2f}</div>", unsafe_allow_html=True)

        gb_ret = GridOptionsBuilder.from_dataframe(df_ret_filtrado[['Lote', 'Manzana', 'Partida', 'Destajista', 'Costo', '% Retención', 'Monto Retenido', 'Liberar_Check', 'Estatus Retención', 'Fecha Liberación', 'Usuario Liberó', '_original_index', 'ID_DB']])
        gb_ret.configure_default_column(sortable=False, filter=True, resizable=True)

        gb_ret.configure_column("_original_index", hide=True)
        gb_ret.configure_column("ID_DB", hide=True)
        gb_ret.configure_column("Estatus Retención", hide=True) 
        
        gb_ret.configure_column("Lote", cellClass='centrar-valor', headerClass='ag-center-header', width=90)
        gb_ret.configure_column("Manzana", cellClass='centrar-valor', headerClass='ag-center-header', width=90)
        gb_ret.configure_column("Costo", valueFormatter="x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})", cellClass='centrar-valor', headerClass='ag-center-header', width=110)
        gb_ret.configure_column("% Retención", valueFormatter="(x*100)+'%'", cellClass='centrar-valor', headerClass='ag-center-header', width=110)
        gb_ret.configure_column("Monto Retenido", valueFormatter="x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})", cellClass='centrar-valor', headerClass='ag-center-header', width=130)
        
        gb_ret.configure_column("Liberar_Check", headerName="Liberar Fondo", editable=True, cellRenderer='agCheckboxCellRenderer', cellEditor='agCheckboxCellEditor', cellClass='centrar-valor', headerClass='ag-center-header', width=120)
        gb_ret.configure_column("Fecha Liberación", cellClass='centrar-valor', headerClass='ag-center-header', width=160)
        gb_ret.configure_column("Usuario Liberó", cellClass='centrar-valor', headerClass='ag-center-header', width=120)

        rowStyleRet = JsCode("""
        function(params) {
            let estatus = params.data['Estatus Retención'];
            if (estatus === 'Liberado') {
                return { 'backgroundColor': 'rgba(16, 185, 129, 0.1)', 'color': '#6EE7B7', 'pointerEvents': 'none', 'borderBottom': '1px solid #10B981' };
            }
            
            let chk = params.data['Liberar_Check'];
            if (chk === true || chk === 'true' || chk === 1) {
                return { 'backgroundColor': 'rgba(245, 158, 11, 0.2)', 'color': '#FCD34D', 'borderBottom': '1px solid #F59E0B' };
            }
            
            return { 'color': '#00FFFF', 'borderBottom': '1px solid #4a4a4a' };
        }
        """)
        gb_ret.configure_grid_options(getRowStyle=rowStyleRet, rowHeight=35)
        
        mis_estilos_ret = {
            ".ag-header-cell-text": {"font-size": "18px !important"},
            ".ag-header-cell-label": {"justify-content": "center !important"},
            ".ag-cell": {"font-size": "16px !important", "display": "flex", "align-items": "center"},
            ".ag-cell-value": {"font-size": "16px !important"},
            ".centrar-valor": {"justify-content": "center !important"},
            ".ag-checkbox-input-wrapper.ag-checked": {"background-color": "#10B981 !important", "border-color": "#10B981 !important"}
        }
        
        response_ret = AgGrid(
            df_ret_filtrado[['Lote', 'Manzana', 'Partida', 'Destajista', 'Costo', '% Retención', 'Monto Retenido', 'Liberar_Check', 'Estatus Retención', 'Fecha Liberación', 'Usuario Liberó', '_original_index', 'ID_DB']].copy(),
            gridOptions=gb_ret.build(),
            key=f"grid_fondos_garantia_{st.session_state.grid_key}",
            reload_data=False,
            enable_enterprise_modules=False,
            allow_unsafe_jscode=True,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            theme='streamlit',
            height=400,
            custom_css=mis_estilos_ret
        )

        if response_ret['data'] is not None and not pd.DataFrame(response_ret['data']).empty:
            df_ret_pantalla = pd.DataFrame(response_ret['data'])
            df_ret_pantalla['Check_Bool'] = df_ret_pantalla['Liberar_Check'].astype(str).str.lower().isin(['true', '1'])
            
            suma_activados = df_ret_pantalla[(df_ret_pantalla['Check_Bool'] == True) & (df_ret_pantalla['Estatus Retención'] != 'Liberado')]['Monto Retenido'].sum()

            ph_suma_naranja.markdown(f"<div style='background-color:#F59E0B; color:black; padding:15px; border-radius:8px; text-align:center; box-shadow: 0px 4px 6px rgba(0,0,0,0.1); margin-top:28px;'><span style='font-size:16px; font-weight:normal;'>Suma a liberar ahora:</span><br><span style='font-size:26px; font-weight:bold;'>${suma_activados:,.2f}</span></div>", unsafe_allow_html=True)
        else:
            ph_suma_naranja.markdown(f"<div style='background-color:#F59E0B; color:black; padding:15px; border-radius:8px; text-align:center; box-shadow: 0px 4px 6px rgba(0,0,0,0.1); margin-top:28px;'><span style='font-size:16px; font-weight:normal;'>Suma a liberar ahora:</span><br><span style='font-size:26px; font-weight:bold;'>$0.00</span></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        c_sav_r1, c_sav_r2, c_sav_r3 = st.columns([3, 4, 3])
        
        with c_sav_r2:
            if st.button("🔓 Procesar Guardado y Generar Recibo", type="primary", use_container_width=True):
                if response_ret['data'] is not None:
                    df_ret_pantalla = pd.DataFrame(response_ret['data'])
                    
                    tz_mx = ZoneInfo("America/Mexico_City")
                    tiempo_actual = datetime.now(tz_mx)
                    meses_3_letras = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
                    ahora_lib = f"{tiempo_actual.strftime('%d')}/{meses_3_letras[tiempo_actual.month]}/{tiempo_actual.strftime('%Y')} {tiempo_actual.strftime('%H:%M:%S')}"
                    usr_lib = str(st.session_state.usuario)
                    
                    cambios_detectados = False
                    df_recibo_nuevo = []
                    
                    st.session_state.df['Fecha Liberación'] = st.session_state.df['Fecha Liberación'].astype(str).replace(['nan', 'NaN', 'NaT', 'None', '<NA>'], '')
                    st.session_state.df['Usuario Liberó'] = st.session_state.df['Usuario Liberó'].astype(str).replace(['nan', 'NaN', 'NaT', 'None', '<NA>'], '')
                    
                    for _, row_p in df_ret_pantalla.iterrows():
                        idx_orig = int(row_p['_original_index'])
                        est_val = row_p['Liberar_Check']
                        
                        if (est_val == True or est_val == 'true' or est_val == 1) and str(st.session_state.df.loc[idx_orig, 'Estatus Retención']) == "Retenido":
                            
                            st.session_state.df.loc[idx_orig, 'Estatus Retención'] = "Liberado"
                            st.session_state.df.loc[idx_orig, 'Fecha Liberación'] = str(ahora_lib)
                            st.session_state.df.loc[idx_orig, 'Usuario Liberó'] = str(usr_lib)
                            
                            df_recibo_nuevo.append(row_p)
                            cambios_detectados = True
                            
                    if cambios_detectados:
                        df_a_imprimir = pd.DataFrame(df_recibo_nuevo)
                        df_a_imprimir['Monto_Num'] = pd.to_numeric(df_a_imprimir['Monto Retenido'], errors='coerce').fillna(0)
                        df_res_imp = df_a_imprimir.groupby('Destajista')['Monto_Num'].sum().reset_index()
                        
                        pdf = FPDF(orientation='P', unit='mm', format='Letter')
                        pdf.add_page()
                                                
                        pdf.set_font("Arial", 'B', 14)
                        pdf.set_text_color(30, 58, 138)
                        pdf.cell(195, 8, txt="REPORTE DE LIBERACIÓN DE FONDOS DE GARANTÍA", ln=True, align='C')
                        
                        # Inyección superior del nombre de la obra en el recibo
                        pdf.set_font("Arial", 'B', 10)
                        pdf.set_text_color(75, 85, 99)
                        pdf.cell(195, 5, txt=f"OBRA: {str(st.session_state.obra_actual).upper()}", ln=True, align='C')
                        
                        pdf.set_font("Arial", 'I', 9)
                        pdf.set_text_color(108, 117, 125)
                        pdf.cell(195, 5, txt=f"Generado el: {ahora_lib} (Zona Horaria México)", ln=True, align='C')
                        pdf.ln(8)
                        
                        pdf.set_font("Arial", 'B', 10)
                        pdf.set_fill_color(30, 58, 138)
                        pdf.set_text_color(255, 255, 255)
                        w_col1, w_col2 = 145, 50
                        pdf.cell(w_col1, 8, txt="Destajista", border=1, align='C', fill=True)
                        pdf.cell(w_col2, 8, txt="Monto Liberado", border=1, align='C', fill=True)
                        pdf.ln(8)
                        
                        pdf.set_font("Arial", '', 9)
                        pdf.set_text_color(0, 0, 0)
                        total_general = 0
                        fondo_cebra = False
                        
                        for _, row_imp in df_res_imp.iterrows():
                            if fondo_cebra:
                                pdf.set_fill_color(245, 247, 250)
                            else:
                                pdf.set_fill_color(255, 255, 255)
                                
                            costo_fila = float(row_imp['Monto_Num'])
                            dest_txt = str(row_imp['Destajista']).strip()
                            if not dest_txt: dest_txt = "Sin Asignar"
                            
                            pdf.cell(w_col1, 7, txt=dest_txt[:80], border=1, align='L', fill=True)
                            pdf.cell(w_col2, 7, txt=f"${costo_fila:,.2f}", border=1, align='R', fill=True)
                            pdf.ln(7)
                            
                            total_general += costo_fila
                            fondo_cebra = not fondo_cebra
                            
                        pdf.set_font("Arial", 'B', 10)
                        pdf.set_fill_color(230, 235, 245)
                        pdf.cell(w_col1, 8, txt="GRAN TOTAL LIBERADO HOY ", border=1, align='R', fill=True)
                        pdf.cell(w_col2, 8, txt=f"${total_general:,.2f}", border=1, align='R', fill=True)
                        
                        st.session_state.ultimo_recibo_pdf = bytes(pdf.output())

                        df_envio_ret = st.session_state.df.copy()
                        if 'Concepto_Limpio' in df_envio_ret.columns:
                            df_envio_ret = df_envio_ret.drop(columns=['Concepto_Limpio'])
                        
                        df_envio_ret['Fecha pago'] = df_envio_ret['Fecha pago'].apply(lambda x: f"'{x}" if str(x).strip() != '' else '')
                        df_envio_ret['Fecha Liberación'] = df_envio_ret['Fecha Liberación'].apply(lambda x: f"'{x}" if str(x).strip() != '' else '')
                        
                        with st.spinner("Registrando liberaciones y sincronizando con Supabase..."):
                            actualizar_datos_gsheet(df_envio_ret)
                            st.session_state.df = obtener_datos_gsheet()
                            
                        st.session_state.df_original = st.session_state.df.copy()
                        st.session_state.grid_key += 1 
                        st.rerun() 
                    else:
                        st.warning("No seleccionaste ninguna partida nueva para liberar.")

        if 'ultimo_recibo_pdf' in st.session_state and st.session_state.ultimo_recibo_pdf is not None:
            st.success("✅ ¡Liberación guardada en Supabase! Las partidas han sido bloqueadas exitosamente.")
            
            c_desc1, c_desc2, c_desc3 = st.columns([3, 4, 3])
            with c_desc2:
                st.download_button(
                    label="📥 DESCARGAR RECIBO DE LA LIBERACIÓN REALIZADA",
                    data=st.session_state.ultimo_recibo_pdf,
                    file_name=f"Recibo_Retenciones_{datetime.now(ZoneInfo('America/Mexico_City')).strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )
                if st.button("❌ Ocultar este recibo", use_container_width=True):
                    st.session_state.ultimo_recibo_pdf = None
                    st.rerun()

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
# PESTAÑA 3: MAPA INTERACTIVO
# =========================================================================
elif menu == "Mapa Interactivo":
    mostrar_cabecera_con_logo("🗺️ Plano Interactivo Dinámico", "Visualización gráfica del avance del desarrollo.")

    df_map_base = df.copy()
    df_map_base['Costo'] = pd.to_numeric(df_map_base['Costo'], errors='coerce').fillna(0)
    df_map_base['Estado'] = df_map_base.apply(lambda r: 'Pagado' if str(r['Fecha pago']).strip() != '' else 'Pendiente', axis=1)

    def hex_to_rgba(hex_val, opacity):
        hex_val = hex_val.lstrip('#')
        if len(hex_val) == 6:
            return f"rgba({int(hex_val[0:2], 16)}, {int(hex_val[2:4], 16)}, {int(hex_val[4:6], 16)}, {opacity})"
        return "rgba(0,0,0,0)"

    # EXTRAEMOS LOS LOTES DINÁMICAMENTE DESDE LA BASE DE DATOS (Adiós a las coordenadas fijas)
    lotes_unicos_bd = sorted([str(x).strip() for x in df_map_base['Lote'].unique() if str(x).strip()], key=natural_sort_key)

    lotes_datos_mapa = []
    for lote_num in lotes_unicos_bd:
        df_lote_mapa = df_map_base[df_map_base['Lote'].astype(str).str.strip() == str(lote_num)].copy()
        
        if not df_lote_mapa.empty:
            total_partidas = len(df_lote_mapa)
            df_lote_mapa['Total_Pagado_Real'] = df_lote_mapa.apply(lambda r: r['Costo'] if r['Estado'] == 'Pagado' else 0, axis=1)
            total_precio_lote = df_lote_mapa['Costo'].sum()
            total_pagado_lote = df_lote_mapa['Total_Pagado_Real'].sum()
            
            porcentaje = (total_pagado_lote / total_precio_lote * 100) if total_precio_lote > 0 else 0
            pagadas_completas = len(df_lote_mapa[df_lote_mapa['Estado'] == 'Pagado'])
            
            if porcentaje == 0:
                color_lote = "🔴 No iniciado"
                hex_color = "#EF4444"      
            elif 0 < porcentaje <= 50:
                color_lote = "⚫ Obra negra"
                hex_color = "#57534E"      
            elif 50 < porcentaje <= 60:
                color_lote = "⚪ Obra gris"
                hex_color = "#752BA7"      
            elif 60 < porcentaje <= 70:
                color_lote = "🟡 Obra blanca"
                hex_color = "#FADE50"      
            elif 70 < porcentaje <= 80:
                color_lote = "🟠 Pisos"
                hex_color = "#F97316"      
            elif 80 < porcentaje <= 95:
                color_lote = "🔵 Equipamientos (avalúos)"
                hex_color = "#3B82F6"      
            else: 
                color_lote = "🟢 Detallado y entrega"
                hex_color = "#10B981"      
                
            lotes_datos_mapa.append({
                "Lote": f"Lote {lote_num}",
                "Lote_Id": str(lote_num),
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
    
    # Generamos las columnas necesarias
    df_map_base['Partida_Num'] = df_map_base['Partida'].apply(extraer_numero_partida)
    # Usamos la Lista Maestra para ordenar los filtros del mapa
    df_map_base['Concepto_Limpio'] = df_map_base['Partida'].apply(limpiar_texto_partida)
    conceptos_mapa = [str(p) for p in df_map_base['Concepto_Limpio'].dropna().unique() if str(p).strip()]
    partidas_ordenadas_limpias = sorted(
        conceptos_mapa,
        key=lambda x: ORDEN_PARTIDAS_MAESTRO.index(x) if x in ORDEN_PARTIDAS_MAESTRO else 99999
    )
    
    destajistas_unicos_filtro = sorted([str(d) for d in df_map_base['Destajista'].dropna().unique() if str(d).strip()], key=natural_sort_key)
    
    filtro_partidas_mapa_display = f_col_mapa1.multiselect(
        "Filtrar por Partida (Máx 4):", 
        options=partidas_ordenadas_limpias,
        max_selections=4
    )
    
    filtro_partidas_mapa = filtro_partidas_mapa_display # Como ya es limpio, no necesitamos hacer el "split" de antes
    
    filtro_destajistas_mapa = f_col_mapa2.multiselect(
        "Filtrar por Destajista (Máx 4):", 
        options=destajistas_unicos_filtro,
        max_selections=4
    )
    
    filtros_activos = bool(filtro_partidas_mapa) or bool(filtro_destajistas_mapa)
    
    df_filtered = df_map_base[df_map_base['Estado'] == 'Pagado'].copy()
    if filtro_partidas_mapa:
        df_filtered = df_filtered[df_filtered['Concepto_Limpio'].isin(filtro_partidas_mapa)]
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
                opciones_selector = ["Mostrar Todos"] + [f"Lote {k}" for k in lotes_unicos_bd]
                
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
                df_resumen_global = df_map_base.copy()
                df_resumen_global['Total_Pagado_Real'] = df_resumen_global.apply(lambda r: r['Costo'] if r['Estado'] == 'Pagado' else 0, axis=1)
                
                df_resumen_global_grp = df_resumen_global.groupby('Lote').agg(
                    Total_Partidas=('Partida', 'count'),
                    Pagadas=('Estado', lambda x: (x == 'Pagado').sum()),
                    Costo_Total=('Costo', 'sum'),
                    Pagado_Acum=('Total_Pagado_Real', 'sum')
                ).reset_index()
                
                # 1. Calculamos el porcentaje
                df_resumen_global_grp['Pct_Numerico'] = (df_resumen_global_grp['Pagado_Acum'] / df_resumen_global_grp['Costo_Total'] * 100).fillna(0)
                
                # 2. Función para asignar colores Hexadecimales puros (¡AQUÍ PUEDES CAMBIAR TUS COLORES!)
                def obtener_color_hex(pct):
                    if pct == 0: return "#EF4444"        # Rojo (No iniciado)
                    elif 0 < pct <= 50: return "#57534E" # Gris Oscuro (Obra negra)
                    elif 50 < pct <= 60: return "#752BA7" # Morado (Obra gris)
                    elif 60 < pct <= 70: return "#FADE50" # Amarillo (Obra blanca)
                    elif 70 < pct <= 80: return "#F97316" # Naranja (Pisos)
                    elif 80 < pct <= 95: return "#3B82F6" # Azul (Equipamientos)
                    else: return "#10B981"                # Verde (Detallado y entrega)

                                    
                df_resumen_global_grp['Color_Hex'] = df_resumen_global_grp['Pct_Numerico'].apply(obtener_color_hex)
                df_resumen_global_grp['% Avance'] = df_resumen_global_grp['Pct_Numerico'].apply(lambda x: f"{x:.1f}%")

                # --- CORRECCIÓN DE ORDENAMIENTO NUMÉRICO (NATURAL) ---
                df_resumen_global_grp['sort_key'] = df_resumen_global_grp['Lote'].apply(natural_sort_key)
                df_resumen_global_grp = df_resumen_global_grp.sort_values(by='sort_key').drop(columns=['sort_key'])
                
                # 3. Construimos la tabla en HTML puro para forzar el centrado y los círculos perfectos
                html_table = (
                    "<div style='height: 480px; overflow-y: auto; font-family: sans-serif; font-size: 14px; width: 100%; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;'>"
                    "<table style='width: 100%; border-collapse: collapse; text-align: center; color: #d1d1d1;'>"
                    "<thead style='position: sticky; top: 0; background-color: #262626; z-index: 10;'>"
                    "<tr>"
                    "<th style='padding: 10px; border-bottom: 2px solid #444; text-align: center;'>Lote</th>"
                    "<th style='padding: 10px; border-bottom: 2px solid #444; text-align: center;'>Total Partidas</th>"
                    "<th style='padding: 10px; border-bottom: 2px solid #444; text-align: center;'>Pagadas</th>"
                    "<th style='padding: 10px; border-bottom: 2px solid #444; text-align: center;'>Costo Total</th>"
                    "<th style='padding: 10px; border-bottom: 2px solid #444; text-align: center;'>% Avance</th>"
                    "<th style='padding: 10px; border-bottom: 2px solid #444; text-align: center;'>Fase</th>"
                    "</tr></thead><tbody>"
                )
                
                for _, row_res in df_resumen_global_grp.iterrows():
                    c_hex = row_res['Color_Hex']
                    
                    html_table += (
                        "<tr style='border-bottom: 1px solid #333;'>"
                        f"<td style='padding: 10px; text-align: center;'>{row_res['Lote']}</td>"
                        f"<td style='padding: 10px; text-align: center;'>{row_res['Total_Partidas']}</td>"
                        f"<td style='padding: 10px; text-align: center;'>{row_res['Pagadas']}</td>"
                        f"<td style='padding: 10px; text-align: center;'>${row_res['Costo_Total']:,.2f}</td>"
                        f"<td style='padding: 10px; text-align: center;'>{row_res['% Avance']}</td>"
                        f"<td style='padding: 10px; vertical-align: middle;'>"
                        f"<div style='width: 18px; height: 18px; border-radius: 50%; background-color: {c_hex}; margin: 0 auto; border: 1px solid rgba(255,255,255,0.2);'></div>"
                        f"</td>"
                        "</tr>"
                    )
                html_table += "</tbody></table></div>"
                
                # Renderizamos la tabla
                st.markdown(html_table, unsafe_allow_html=True)
        else:
            lote_puro_num = str(st.session_state.lote_actual)
            
            if filtros_activos:
                st.markdown(f"**Desglose Filtrado (Lote {lote_puro_num}):**")
                df_desglose_lote = df_filtered[df_filtered['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Costo', 'Concepto_Limpio']].copy()
            else:
                st.markdown(f"**Desglose General (Lote {lote_puro_num}):**")
                df_desglose_lote = df_map_base[df_map_base['Lote'].astype(str).str.strip() == lote_puro_num][['Partida', 'Estado', 'Costo', 'Concepto_Limpio']].copy()
            
            # ORDENAMOS desglose del lote usando la lista maestra y ocultamos el número
            if not df_desglose_lote.empty:
                df_desglose_lote['Orden_Excel'] = df_desglose_lote['Concepto_Limpio'].apply(
                    lambda x: ORDEN_PARTIDAS_MAESTRO.index(x) if x in ORDEN_PARTIDAS_MAESTRO else 99999
                )
                df_desglose_lote = df_desglose_lote.sort_values('Orden_Excel')
                df_desglose_lote['Partida'] = df_desglose_lote['Concepto_Limpio'] # Desaparece número




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
        nombre_dinamico = f"SVG_{st.session_state.obra_actual}.txt"
        nombres_posibles = [nombre_dinamico, "SVGsembrado.txt"] # Busca el de la obra, si no lo halla busca el genérico
        archivo_encontrado = None
        
        for nombre in nombres_posibles:
            if os.path.exists(nombre):
                archivo_encontrado = nombre
                break
                
        if archivo_encontrado:
            try:
                with open(archivo_encontrado, "r", encoding="utf-8") as f:
                    svg_content = f.read()           
                                
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
                        
                        avance_lote = item["Avance"]
                        fase_lote = item["Estado"]
                        
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

            ancho_celda = 35
            alto_celda = 20
            
            for i, row in enumerate(df_lote_diag.itertuples()):
                col_actual = i % cols
                fila_actual = i // cols
                
                x = (col_actual * ancho_celda) + (ancho_celda / 2.0)
                y = (fila_actual * alto_celda) + (alto_celda / 2.0)
                    
                x_coords.append(x)
                y_coords.append(y)

                estado = row.Estado
                costo = row.Costo 
                pago_real = costo if estado == 'Pagado' else 0.0 
                destajista = row.Destajista if pd.notna(row.Destajista) and row.Destajista != "" else "Sin Asignar"
                
                color_asignado = mapa_colores_partida.get(row.Partida, "#3B82F6")

                if estado == "Pagado":
                    colores_relleno.append(color_asignado)
                else:
                    colores_relleno.append("rgba(0,0,0,0)") 

                hover_text = f"<b>Partida:</b> {row.Partida}<br><b>Costo Total:</b> ${costo:,.2f}<br><b>Pagado:</b> ${pago_real:,.2f}<br><b>Destajista:</b> {destajista}<br><b>Estado:</b> {estado}"
                textos_hover.append(hover_text)

            diametro_esfera_px = 40
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
                    line=dict(width=1, color="#374151") 
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


# =========================================================================
# PESTAÑA #5: VISOR MÓVIL (KPIs RESPONSIVOS)
# =========================================================================
elif menu == "Visor Móvil":
    mostrar_cabecera_con_logo(f"📱 Resumen de Obra: {st.session_state.obra_actual}")
    st.write("Visor optimizado para lectura rápida en dispositivos móviles.")

    df_movil = st.session_state.df.copy()
    
    if df_movil.empty:
        st.info("No hay datos registrados en esta obra aún.")
    else:
        # Cálculos generales
        df_movil['Costo_Num'] = pd.to_numeric(df_movil['Costo'], errors='coerce').fillna(0)
        df_movil['Total_Pagado'] = df_movil.apply(lambda r: r['Costo_Num'] if str(r['Fecha pago']).strip() != '' else 0, axis=1)
        
        gran_total = df_movil['Costo_Num'].sum()
        pagado_total = df_movil['Total_Pagado'].sum()
        por_pagar = gran_total - pagado_total
        pct_avance = (pagado_total / gran_total * 100) if gran_total > 0 else 0

        # Tarjetas principales (Streamlit las apila verticalmente en celulares)
        st.markdown("### 💰 Estatus Financiero General")
        c1, c2, c3 = st.columns(3)
        c1.metric("Presupuesto Total", f"${gran_total:,.2f}")
        c2.metric("Total Pagado", f"${pagado_total:,.2f}", f"{pct_avance:.1f}% Avance")
        c3.metric("Deuda Pendiente", f"${por_pagar:,.2f}", delta="-", delta_color="inverse")
        
        st.progress(pct_avance / 100)
        st.markdown("<hr>", unsafe_allow_html=True)

        # Filtro simplificado nativo (amigable para el dedo en pantallas táctiles)
        st.markdown("### 🏠 Desglose Rápido por Lote")
        lotes_disp = sorted([str(x) for x in df_movil['Lote'].unique() if str(x).strip()], key=natural_sort_key)
        lote_sel = st.selectbox("Selecciona un lote para ver su avance:", ["Resumen de todos"] + lotes_disp)

        if lote_sel != "Resumen de todos":
            df_lote = df_movil[df_movil['Lote'].astype(str) == lote_sel]
            costo_l = df_lote['Costo_Num'].sum()
            pago_l = df_lote['Total_Pagado'].sum()
            pend_l = costo_l - pago_l
            
            st.info(f"**Prototipo:** {df_lote['Prototipo'].iloc[0]}")
            
            cl1, cl2 = st.columns(2)
            cl1.metric("Costo del Lote", f"${costo_l:,.2f}")
            cl2.metric("Pagado", f"${pago_l:,.2f}")
            st.error(f"Falta por pagar: **${pend_l:,.2f}**")
        else:
            # Lista simple top 5 deudores para no saturar la pantalla
            st.markdown("##### 👷 Top 5 Contratistas con saldo pendiente")
            df_deudores = df_movil[df_movil['Total_Pagado'] < df_movil['Costo_Num']].copy()
            df_deudores['Deuda'] = df_deudores['Costo_Num'] - df_deudores['Total_Pagado']
            deuda_por_dest = df_deudores.groupby('Destajista')['Deuda'].sum().sort_values(ascending=False).head(5)
            
            for destajista, deuda in deuda_por_dest.items():
                nombre = destajista if str(destajista).strip() else "Sin Asignar"
                st.markdown(f"- **{nombre}:** ${deuda:,.2f}")