
import pandas as pd
import requests
import json
import os

with open("shopify_config.json") as f:
    config = json.load(f)

SHOP_URL = config["shop_url"]
ACCESS_TOKEN = config["access_token"]
API_VERSION = "2023-07"

CSV_PATH = "csv-input/visiotech.csv"
MARCAS_PERMITIDAS = ["AJAX", "AJAXCCTV", "AJAXVIVIENDAVACÍA", "AQARA", "REOLINK", "YALE"]
CATEGORIAS_EXCLUIDAS = ["Armazenamento em nuvem Ajax", "Outlet", "Peças de reposição"]

def convert_stock(value):
    return {"high": 10, "medium": 5, "low": 2, "none": 0}.get(str(value).strip().lower(), 0)

def aplicar_iva_e_transporte(preco_custo):
    if preco_custo <= 10:
        margem = 0.6
    elif preco_custo <= 20:
        margem = 0.5
    elif preco_custo <= 40:
        margem = 0.4
    elif preco_custo <= 80:
        margem = 0.3
    else:
        margem = 0.25
    preco_venda = preco_custo * (1 + margem)
    preco_final = round(preco_venda * 1.23 + 7, 2)
    return preco_final

def obter_produtos_shopify():
    headers = {"X-Shopify-Access-Token": ACCESS_TOKEN}
    url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/products.json?limit=250"
    response = requests.get(url, headers=headers)
    return response.json().get("products", []) if response.status_code == 200 else []

def criar_ou_atualizar_produto(row, produtos_shopify):
    ean = row["ean"] if pd.notna(row["ean"]) else ""
    sku = ean if ean else row["name"]
    handle = row["name"]
    stock = convert_stock(row["stock"])
    preco_custo = float(row["precio_neto_compra"])
    preco_venda = aplicar_iva_e_transporte(preco_custo)

    produto_encontrado = None
    for p in produtos_shopify:
        for variante in p.get("variants", []):
            if variante.get("sku") == sku or p.get("handle") == handle:
                produto_encontrado = {"id": p["id"], "variant_id": variante["id"]}
                break

    headers = {
        "X-Shopify-Access-Token": ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    if produto_encontrado:
        variant_data = {
            "variant": {
                "id": produto_encontrado["variant_id"],
                "price": preco_venda,
                "inventory_quantity": stock
            }
        }
        url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/variants/{produto_encontrado['variant_id']}.json"
        response = requests.put(url, headers=headers, data=json.dumps(variant_data))
    else:
        nome = row["short_description"]
        descricao = row["description"]
        especificacoes = row["specifications"] if pd.notna(row["specifications"]) else ""
        descricao_final = f"{descricao}<br><br><strong>Especificações Técnicas:</strong><br>{especificacoes}"
        imagem_principal = row["image_path"]
        marca_original = row["brand"]
        marca = "Ajax" if marca_original.upper() in ["AJAX", "AJAXCCTV", "AJAXVIVIENDAVACÍA"] else marca_original
        tags = marca
        tipo = row["category"] if "category" in row and pd.notna(row["category"]) else marca
        imagens_extra = []
        try:
            imagens_extra = json.loads(row["extra_images_paths"]).get("details", [])
        except:
            pass

        dados_produto = {
            "product": {
                "title": nome,
                "body_html": descricao_final,
                "vendor": marca,
                "product_type": tipo,
                "tags": tags,
                "handle": handle,
                "images": [{"src": imagem_principal}] + [{"src": img} for img in imagens_extra],
                "variants": [{
                    "sku": sku,
                    "barcode": ean if ean else "",
                    "price": preco_venda,
                    "inventory_quantity": stock,
                    "inventory_management": "shopify",
                    "cost": preco_custo
                }]
            }
        }

        url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/products.json"
        response = requests.post(url, headers=headers, data=json.dumps(dados_produto))

    if response.status_code in [200, 201]:
        print(f"✔ Produto {'atualizado' if produto_encontrado else 'criado'} com sucesso: {sku}")
    else:
        print(f"❌ Erro ({response.status_code}) ao sincronizar {sku}: {response.text}")

if __name__ == "__main__":
    if not os.path.exists(CSV_PATH):
        print(f"❌ Ficheiro CSV não encontrado: {CSV_PATH}")
        exit()

    df = pd.read_csv(CSV_PATH, sep=";", encoding="utf-8", low_memory=False)
    df = df[df["brand"].str.upper().isin(MARCAS_PERMITIDAS)]
    df = df[~df["category"].isin(CATEGORIAS_EXCLUIDAS)]

    produtos_shopify = obter_produtos_shopify()

    for i, (_, row) in enumerate(df.iterrows()):
        criar_ou_atualizar_produto(row, produtos_shopify)
