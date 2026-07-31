import sqlite3
from datetime import datetime
import streamlit as st
import numpy as np
from PIL import Image
import io
import pandas as pd
import face_recognition

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
DB_NAME = "ponto_eletronico.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS funcoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            valor REAL NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profissionais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            documento TEXT UNIQUE NOT NULL,
            funcao TEXT NOT NULL,
            chave_pix TEXT NOT NULL,
            foto BLOB,
            face_encoding BLOB
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT NOT NULL,
            data_dia TEXT NOT NULL,
            id_profissional INTEGER NOT NULL,
            nome TEXT NOT NULL,
            funcao TEXT NOT NULL,
            valor REAL NOT NULL,
            pix TEXT NOT NULL,
            foto_ponto BLOB,
            latitude REAL,
            longitude REAL,
            status_facial TEXT,
            FOREIGN KEY (id_profissional) REFERENCES profissionais (id)
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM funcoes")
    if cursor.fetchone()[0] == 0:
        funcoes_iniciais = [
            ("Encarregado", 300.0),
            ("Pedreiro", 250.0),
            ("Pintor", 250.0),
            ("Meio Oficial", 200.0),
            ("Ajudante", 150.0)
        ]
        cursor.executemany("INSERT INTO funcoes (nome, valor) VALUES (?, ?)", funcoes_iniciais)
    else:
        cursor.execute("INSERT OR IGNORE INTO funcoes (nome, valor) VALUES ('Encarregado', 300.0)")
        
    conn.commit()
    conn.close()

init_db()

def get_funcoes():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, valor FROM funcoes")
    data = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in data}

def get_profissionais():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, documento, funcao, chave_pix, foto, face_encoding FROM profissionais")
    data = cursor.fetchall()
    conn.close()
    return data

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="PontoObraMads", layout="centered")

st.title("🏗️ PontoObraMads - Controle de Diárias")

# --- CONTROLE DE ACESSO (LOGIN) NA BARRA LATERAL ---
st.sidebar.header("🔐 Acesso ao Sistema")
tipo_usuario = st.sidebar.selectbox("Selecione o Perfil", ["Selecione...", "👷 Coordenador", "🔑 Administrador (Admin)"])

data_hoje = datetime.now().strftime("%Y-%m-%d")
horario_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if tipo_usuario == "Selecione...":
    st.info("👈 Por favor, selecione o seu perfil de acesso no menu lateral (Coordenador ou Administrador) para começar.")

# ==========================================
# PERFIL: COORDENADOR
# ==========================================
elif tipo_usuario == "👷 Coordenador":
    st.sidebar.divider()
    st.sidebar.subheader("Menu do Coordenador")
    menu_coord = st.sidebar.radio("Escolha a Ação", ["📸 Registrar Ponto", "➕ Cadastrar Profissional", "✏️ Editar Cadastro"])
    
    if menu_coord == "📸 Registrar Ponto":
        st.header("📸 Registro de Ponto com Biometria e GPS")
        st.info("Selecione o profissional, tire a foto e capture a localização para registrar o ponto.")
        
        profissionais = get_profissionais()
        
        if not profissionais:
            st.warning("Nenhum profissional cadastrado no sistema.")
        else:
            nomes_profissionais = [p[1] for p in profissionais]
            prof_selecionado = st.selectbox("Selecione o Profissional", nomes_profissionais)
            
            dados_prof = next(p for p in profissionais if p[1] == prof_selecionado)
            prof_id = dados_prof[0]
            funcao_prof = dados_prof[3]
            pix_prof = dados_prof[4]
            cad_encoding_blob = dados_prof[6]
            
            funcoes_dict = get_funcoes()
            valor_diaria = funcoes_dict.get(funcao_prof, 0.0)
            
            st.write(f"**Função:** {funcao_prof}")
            
            # Coordenadas GPS via Streamlit components (ou input manual/simulado se indisponível no browser)
            st.markdown("📍 **Localização GPS da Obra**")
            lat = st.number_input("Latitude", value=-23.5505, format="%.6f")
            lon = st.number_input("Longitude", value=-46.6333, format="%.6f")
            
            foto_capturada = st.camera_input("Tire a foto para bater o ponto")
            
            if foto_capturada is not None:
                image_bytes = foto_capturada.getvalue()
                
                # Processamento de Reconhecimento Facial
                if not cad_encoding_blob:
                    st.error("⚠️ Este profissional não possui vetor facial cadastrado. Atualize o cadastro dele tirando uma foto nítida.")
                else:
                    try:
                        # Converter imagem capturada para array numpy
                        img_ponto_pil = Image.open(io.BytesIO(image_bytes))
                        img_ponto_np = np.array(img_ponto_pil)
                        
                        locs_ponto = face_recognition.face_locations(img_ponto_np)
                        if not locs_ponto:
                            st.error("❌ Nenhum rosto detectado na foto do ponto. Tente novamente com boa iluminação.")
                        else:
                            encoding_ponto = face_recognition.face_encodings(img_ponto_np, locs_ponto)[0]
                            encoding_cadastrado = np.frombuffer(cad_encoding_blob, dtype=np.float64)
                            
                            # Comparar rostos (tolerância 0.6 padrão)
                            match = face_recognition.compare_faces([encoding_cadastrado], encoding_ponto, tolerance=0.6)[0]
                            
                            if not match:
                                st.error("🚨 ERRO: O rosto na foto NÃO corresponde ao profissional cadastrado! Ponto recusado.")
                            else:
                                conn = sqlite3.connect(DB_NAME)
                                cursor = conn.cursor()
                                
                                cursor.execute("SELECT id FROM registros WHERE data_dia = ? AND id_profissional = ?", (data_hoje, prof_id))
                                ja_registrado = cursor.fetchone()
                                
                                if ja_registrado:
                                    st.warning(f"⚠️ O profissional {prof_selecionado} já registrou ponto hoje ({data_hoje}).")
                                else:
                                    cursor.execute("""
                                        INSERT INTO registros (data_hora, data_dia, id_profissional, nome, funcao, valor, pix, foto_ponto, latitude, longitude, status_facial)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (horario_atual, data_hoje, prof_id, prof_selecionado, funcao_prof, valor_diaria, pix_prof, image_bytes, lat, lon, "Aprovado"))
                                    conn.commit()
                                    st.success(f"✅ Ponto validado por Reconhecimento Facial e registrado às {datetime.now().strftime('%H:%M:%S')}!")
                                    st.balloons()
                                conn.close()
                    except Exception as e:
                        st.error(f"Erro ao processar biometria facial: {e}")

    elif menu_coord == "➕ Cadastrar Profissional":
        st.header("➕ Cadastrar Novo Profissional (com Biometria)")
        funcoes_dict = get_funcoes()
        
        with st.form("form_cadastro"):
            nome = st.text_input("Nome Completo")
            documento = st.text_input("CPF (Único)")
            funcao = st.selectbox("Função", list(funcoes_dict.keys()))
            chave_pix = st.text_input("Chave Pix")
            foto_cadastro = st.camera_input("Tirar Foto de Perfil (Foco nítido e centralizado no rosto)")
            
            submitted = st.form_submit_button("Salvar Cadastro")
            
            if submitted:
                if nome and documento and chave_pix and foto_cadastro:
                    try:
                        img_cad_pil = Image.open(foto_cadastro)
                        img_cad_np = np.array(img_cad_pil)
                        
                        locs = face_recognition.face_locations(img_cad_np)
                        if not locs:
                            st.error("❌ Nenhum rosto encontrado na foto de cadastro. Tire outra foto nítida.")
                        else:
                            encoding = face_recognition.face_encodings(img_cad_np, locs)[0]
                            encoding_bytes = encoding.tobytes()
                            foto_bytes = foto_cadastro.getvalue()
                            
                            conn = sqlite3.connect(DB_NAME)
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO profissionais (nome, documento, funcao, chave_pix, foto, face_encoding)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (nome, documento, funcao, chave_pix, foto_bytes, encoding_bytes))
                            conn.commit()
                            conn.close()
                            st.success(f"Profissional {nome} cadastrado com sucesso com biometria facial!")
                    except Exception as e:
                        st.error(f"Erro ao salvar cadastro: {e}")
                else:
                    st.error("Preencha todos os campos e tire a foto.")

    elif menu_coord == "✏️ Editar Cadastro":
        st.header("✏️ Editar Cadastro de Profissional")
        profissionais = get_profissionais()
        
        if not profissionais:
            st.warning("Nenhum profissional cadastrado para editar.")
        else:
            nomes_profissionais = [p[1] for p in profissionais]
            prof_edicao = st.selectbox("Selecione o Profissional", nomes_profissionais)
            
            dados_atuais = next(p for p in profissionais if p[1] == prof_edicao)
            prof_id = dados_atuais[0]
            nome_atual = dados_atuais[1]
            doc_atual = dados_atuais[2]
            func_atual = dados_atuais[3]
            pix_atual = dados_atuais[4]
            
            funcoes_dict = get_funcoes()
            
            with st.form("form_edicao"):
                novo_nome = st.text_input("Nome Completo", value=nome_atual)
                novo_doc = st.text_input("CPF", value=doc_atual)
                
                lista_funcs = list(funcoes_dict.keys())
                idx_func = lista_funcs.index(func_atual) if func_atual in lista_funcs else 0
                nova_funcao = st.selectbox("Função", lista_funcs, index=idx_func)
                
                nova_chave_pix = st.text_input("Chave Pix", value=pix_atual)
                
                atualizar_btn = st.form_submit_button("Atualizar Dados")
                
                if atualizar_btn:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE profissionais 
                        SET nome = ?, documento = ?, funcao = ?, chave_pix = ?
                        WHERE id = ?
                    """, (novo_nome, novo_doc, nova_funcao, nova_chave_pix, prof_id))
                    conn.commit()
                    conn.close()
                    st.success(f"Cadastro de {novo_nome} atualizado com sucesso!")
                    st.rerun()

# ==========================================
# PERFIL: ADMINISTRADOR
# ==========================================
elif tipo_usuario == "🔑 Administrador (Admin)":
    st.sidebar.divider()
    st.sidebar.subheader("Menu do Administrador")
    menu_admin = st.sidebar.radio("Escolha a Ação", ["📋 Relatórios e Filtros", "⚙️ Gerenciar Funções e Valores", "👷 Ver Profissionais Cadastrados"])
    
    if menu_admin == "📋 Relatórios e Filtros":
        st.header("📋 Relatórios de Frequência, Biometria e GPS")
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT data_hora, nome, funcao, valor, pix, foto_ponto, latitude, longitude, status_facial FROM registros ORDER BY data_hora DESC")
        registros = cursor.fetchall()
        conn.close()
        
        if not registros:
            st.info("Nenhum registro de ponto encontrado até o momento.")
        else:
            nomes_unicos = sorted(list(set([r[1] for r in registros])))
            filtro_nome = st.selectbox("Filtrar por Profissional", ["Todos"] + nomes_unicos)
            
            st.divider()
            total_geral = 0.0
            
            for reg in registros:
                data_hora, nome, funcao, valor, pix, foto_bytes, lat, lon, status_facial = reg
                
                if filtro_nome != "Todos" and nome != filtro_nome:
                    continue
                
                total_geral += valor
                
                col_foto, col_info = st.columns([1, 2])
                
                with col_foto:
                    if foto_bytes:
                        try:
                            img = Image.open(io.BytesIO(foto_bytes))
                            st.image(img, caption=f"Ponto de {nome}", width=150)
                        except Exception:
                            st.write("Erro ao carregar foto")
                    else:
                        st.write("Sem foto")
                        
                with col_info:
                    st.markdown(f"**👤 Nome:** {nome}")
                    st.markdown(f"**🛠️ Função:** {funcao}")
                    st.markdown(f"**📅 Data/Hora:** {data_hora}")
                    st.markdown(f"**💰 Diária:** R$ {valor:.2f}")
                    st.markdown(f"**📱 Pix:** {pix}")
                    st.markdown(f"**📍 GPS:** `{lat}, {lon}`")
                    st.markdown(f"**🔒 Validação Facial:** ✅ {status_facial}")
                
                st.divider()
                
            st.metric(label="Total Acumulado a Pagar (Filtro Atual)", value=f"R$ {total_geral:.2f}")

    elif menu_admin == "⚙️ Gerenciar Funções e Valores":
        st.header("⚙️ Gerenciamento de Funções e Valores")
        funcoes_dict = get_funcoes()
        
        st.subheader("Valores Atuais")
        for func, val in funcoes_dict.items():
            st.write(f"- **{func}**: R$ {val:.2f}")
            
        st.divider()
        with st.form("form_funcao"):
            nova_funcao = st.text_input("Nome da Nova Função (ou existente para atualizar)")
            novo_valor = st.number_input("Valor da Diária (R$)", min_value=0.0, step=10.0)
            btn_salvar_funcao = st.form_submit_button("Salvar Função")
            
            if btn_salvar_funcao:
                if nova_funcao and novo_valor > 0:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO funcoes (nome, valor) VALUES (?, ?)
                        ON CONFLICT(nome) DO UPDATE SET valor=excluded.valor
                    """, (nova_funcao, novo_valor))
                    conn.commit()
                    conn.close()
                    st.success(f"Função '{nova_funcao}' salva com o valor de R$ {novo_valor:.2f}!")
                    st.rerun()
                else:
                    st.error("Preencha o nome da função e um valor válido.")

    elif menu_admin == "👷 Ver Profissionais Cadastrados":
        st.header("👷 Lista de Profissionais no Sistema")
        profissionais = get_profissionais()
        
        if not profissionais:
            st.info("Nenhum profissional cadastrado.")
        else:
            # Omitindo blobs pesados no dataframe visual
            df_prof = pd.DataFrame(profissionais, columns=["ID", "Nome", "Documento", "Função", "Chave Pix", "Foto Blob", "Encoding Blob"])
            df_exibicao = df_prof.drop(columns=["Foto Blob", "Encoding Blob"])
            st.dataframe(df_exibicao, use_container_width=True)
