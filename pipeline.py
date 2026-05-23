#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pipeline de détection de Frustrations Reddit Multilingue (EN/FR/ES)
------------------------------------------------------------------
Rôle: Scraper Reddit via RSS, pré-filtrer localement la friction (SaaS & Physique),
      réguler les quotas d'IA, valider sémantiquement, puis stocker les opportunités.
"""

import os
import json
import time
import re
from datetime import datetime
from dotenv import load_dotenv
import requests
import feedparser
from google import genai
from google.genai import types

# Charger les variables d'environnement (.env)
load_dotenv()

# =====================================================================
# INITIALISATION DES SERVICES
# =====================================================================

required_env_vars = ["GEMINI_API_KEY"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    raise ValueError(f"Variable d'environnement manquante dans le fichier .env : {', '.join(missing_vars)}")

# Initialisation du client Google GenAI
ai_client = genai.Client()

# Headers de navigateur pour contourner poliment les restrictions des flux RSS
RSS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# =====================================================================
# GESTION DES CONFIGURATIONS ET FICHIERS
# =====================================================================

def load_config():
    """Charge les subreddits, mots-clés et limites d'optimisation depuis config.json."""
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "subreddits": ["productivity", "EDC", "france"],
        "trigger_keywords": ["alternative", "manuellement", "encombrant"],
        "min_soi_threshold": 75,
        "optimization": {
          "max_queries_per_minute": 12,
          "delay_between_queries_seconds": 5.0,
          "local_prefilter_score_threshold": 25,
          "gemini_retry_attempts": 3,
          "gemini_retry_delay_seconds": 10
        }
    }

def load_database():
    """Charge l'historique des frustrations détectées."""
    db_file = "detected_frustrations.json"
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[!] Base de données corrompue. Réinitialisation...")
            return []
    return []

def save_database(data):
    """Sauvegarde la base de données mise à jour."""
    with open("detected_frustrations.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# =====================================================================
# ALGORITHME DE PRÉ-FILTRAGE LOCAL ÉQUITABLE (ZÉRO APPEL API)
# =====================================================================

def calculate_local_frustration_score(title, content):
    """
    Analyse le post localement et lui attribue une note de friction.
    Équilibre le score pour cibler AUSSI BIEN les frustrations logicielles que matérielles.
    """
    score = 0
    text_lower = f"{title} {content}".lower()
    
    # Matrice de poids multilingue et multi-catégorielle
    keyword_weights = {
        # --- BLOC LOGICIEL / AUTOMATISATION ---
        # Anglais
        "alternative to": 15, "why is there no": 15, "is there an app": 10,
        "manually": 20, "hate doing this": 25, "workaround": 15, "waste of time": 20,
        "how to automate": 15,
        # Français
        "alternative à": 15, "pourquoi personne": 15, "existe-t-il une": 10,
        "manuellement": 20, "marre de": 25, "galère": 15, "perte de temps": 20,
        "comment automatiser": 15,
        # Espagnol
        "alternativa a": 15, "por qué nadie": 15, "existe alguna": 10,
        "manualmente": 20, "harto de": 25, "pérdida de tiempo": 20,
        "cómo automatizar": 15,

        # --- BLOC MATÉRIEL / GADGETS / VIE QUOTIDIENNE ---
        # Anglais
        "tangled": 25, "bulky": 20, "heavy": 15, "broken": 15, "shattered": 20,
        "spilled": 20, "cumbersome": 25, "takes too much space": 20, "cluttered": 15,
        "scratched": 15, "hard to clean": 20, "lost my": 15, "messy": 15,
        # Français
        "s'emmêle": 25, "encombrant": 20, "lourd": 15, "cassé": 15, "prend trop de place": 20,
        "dur à nettoyer": 20, "perdu mes": 15, "renversé": 20, "galère à ranger": 20,
        "rayé": 15, "salissant": 15, "fragile": 15,
        # Espagnol
        "incómodo": 20, "pesado": 15, "se rompió": 15, "ocupa mucho espacio": 20,
        "difícil de limpiar": 20, "enredado": 25, "perdí mi": 15, "manchado": 15
    }
    
    # Évaluation de la présence des mots-clés
    for kw, weight in keyword_weights.items():
        if kw in text_lower:
            score += weight
            
    # Pénalité ou bonus sur la longueur (les textes trop courts manquent de contexte pour l'IA)
    word_count = len(text_lower.split())
    if word_count < 15:
        score -= 15  # Pénalise fortement les posts d'une phrase
    elif 30 <= word_count <= 250:
        score += 5   # Bonus pour les posts bien argumentés
        
    return score

# =====================================================================
# EVALUATION SÉMANTIQUE PAR IA AVEC BACKOFF ET LIMITATION
# =====================================================================

def calculate_soi(gravity, frequency, resolution, accessibility):
    """Calcule le Score d'Opportunité d'Idéation (SOI)."""
    divisor = 11 - resolution
    if divisor <= 0:
        divisor = 1
    return round((gravity * frequency * accessibility) / divisor)

def evaluate_post_with_ai_retry(title, content, subreddit, url, opt_config):
    """
    Appelle l'API Gemini avec gestion robuste des erreurs de quota (429)
    et mécanisme de repli (backoff temporel exponentiel).
    """
    system_prompt = (
        "Tu es un agent d'étude de marché d'élite. Ton but est d'analyser un post Reddit "
        "(en anglais, espagnol ou français) et de déterminer s'il exprime une véritable frustration "
        "exploitable pour un créateur indépendant afin de lancer un produit (SaaS, physique, hybride).\n\n"
        "DIRECTIVES EXTRÊMEMENT STRICTES DE FAISABILITÉ :\n"
        "Tu dois IMPÉRATIVEMENT rejeter (is_valid_pain = false) les problèmes qui sont :\n"
        "1. Insolubles techniquement (ex: enfreindre les lois de la physique, batteries infinies).\n"
        "2. Matériellement hors de portée d'un solopreneur (ex: nécessite de lourdes infrastructures physiques, "
        "des modifications de systèmes d'exploitation verrouillés, ou des autorisations réglementaires lourdes).\n"
        "3. De simples expressions de colère passagère ou des questions génériques.\n\n"
        "Si le problème est valide, génère obligatoirement le titre ('title_fr'), le résumé ('summary_fr') "
        "et l'idée de solution MVP ('proposed_solution_fr') en FRANÇAIS. L'idée de solution doit être réaliste, "
        "concrète, ingénieuse et réalisable à bas coût."
    )

    prompt = f"""
    Analyse ce post issu du subreddit r/{subreddit} (Langue d'origine possible : EN, ES, FR) :
    Titre original : {title}
    Contenu original : {content}
    URL : {url}
    """

    response_schema = {
        "type": "OBJECT",
        "properties": {
            "is_valid_pain": {
                "type": "BOOLEAN",
                "description": "True si le problème est réel, exploitable et techniquement/matériellement simple à résoudre pour un créateur seul."
            },
            "title_fr": {
                "type": "STRING",
                "description": "Titre synthétique du problème rédigé en français."
            },
            "category": {
                "type": "STRING",
                "enum": ["Micro-SaaS", "Objet Physique", "Hybride (HW/SW)"],
                "description": "Catégorie la plus adaptée pour la solution."
            },
            "gravity": {
                "type": "INTEGER",
                "description": "Note de 1 à 10 de la douleur engendrée."
            },
            "frequency": {
                "type": "INTEGER",
                "description": "Note de 1 à 10 de la récurrence du problème."
            },
            "resolution_ease": {
                "type": "INTEGER",
                "description": "Note de 1 à 10 de la facilité à concevoir un MVP simple (ex: pour un objet physique, un prototype imprimable en 3D, découpable au laser ou cousu)."
            },
            "accessibility": {
                "type": "INTEGER",
                "description": "Note de 1 à 10 de la facilité à distribuer le produit dans ce canal ou cette communauté."
            },
            "summary_fr": {
                "type": "STRING",
                "description": "Résumé et contexte de la frustration rédigé en français."
            },
            "proposed_solution_fr": {
                "type": "STRING",
                "description": "Proposition concrète et simple d'une solution MVP faisable rapidement et à bas coût (ex: extension Chrome, script, pièce 3D simple, modèle Notion)."
            },
            "target_persona": {
                "type": "STRING",
                "description": "Qui souffre de ce problème (en français)."
            }
        },
        "required": [
            "is_valid_pain", "title_fr", "category", "gravity", 
            "frequency", "resolution_ease", "accessibility", "summary_fr", "proposed_solution_fr", "target_persona"
        ]
    }

    attempts = opt_config.get("gemini_retry_attempts", 3)
    current_delay = opt_config.get("gemini_retry_delay_seconds", 10)

    for attempt in range(attempts):
        try:
            # Appel API Gemini 2.5 Flash
            response = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=0.1
                )
            )
            
            result = json.loads(response.text)
            
            if result.get("is_valid_pain"):
                result["soi"] = calculate_soi(
                    result["gravity"],
                    result["frequency"],
                    result["resolution_ease"],
                    result["accessibility"]
                )
                return result
            return None

        except Exception as e:
            # Si nous rencontrons une erreur de limite (Code HTTP 429 ou quota)
            print(f"[IA] Quota ou erreur API rencontrée (Tentative {attempt+1}/{attempts}) : {e}")
            if attempt < attempts - 1:
                print(f"[IA] Pause de sécurité et réessai dans {current_delay} secondes...")
                time.sleep(current_delay)
                current_delay *= 2  # Doublement du temps d'attente (Backoff exponentiel)
            else:
                print("[!] Limite maximale de tentatives atteinte. Saut de ce post.")
    
    return None

# =====================================================================
# CORE PIPELINE RUNNER
# =====================================================================

def clean_html(raw_html):
    """Supprime les balises HTML contenues dans les flux RSS."""
    cleanr = re.compile('<.*?>')
    text = re.sub(cleanr, ' ', raw_html)
    text = re.sub(r'submitted by.*?\s', '', text)
    return " ".join(text.split())

def run_pipeline():
    config = load_config()
    database = load_database()
    opt = config.get("optimization", {})
    
    known_ids = {item["id"] for item in database}
    new_discoveries = 0
    
    # Paramètres d'optimisation
    local_threshold = opt.get("local_prefilter_score_threshold", 25)
    query_delay = opt.get("delay_between_queries_seconds", 5.0)
    
    print("=" * 70)
    print(f"LANCEMENT DU PIPELINE OPTIMISÉ (QUOTA SAFE) : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"[+] Seuil local d'exclusion pré-API : {local_threshold} pts")
    print(f"[+] Temporisation stricte entre requêtes : {query_delay} secondes")
    
    for sub_name in config["subreddits"]:
        print(f"\n[Scraper] Analyse de r/{sub_name}...")
        
        # Nous interrogeons le flux RSS de recherche historique du subreddit
        # pour obtenir des posts hautement pertinents sur l'année écoulée
        for kw in config["trigger_keywords"][:4]: # Limite aux 4 premiers mots-clés par subreddit pour économiser le trafic
            try:
                query = requests.utils.quote(kw)
                url = f"https://www.reddit.com/r/{sub_name}/search.rss?q={query}&restrict_sr=1&sort=relevance&t=year"
                response = requests.get(url, headers=RSS_HEADERS, timeout=10)
                
                if response.status_code == 200:
                    feed = feedparser.parse(response.text)
                    
                    for entry in feed.entries:
                        post_id = entry.link.split("/")[-3] if "comments" in entry.link else entry.id
                        if post_id in known_ids:
                            continue
                        
                        clean_content = clean_html(entry.get("summary", ""))
                        
                        # --- ÉTAPE OPTIMISATION 1 : CALCUL DU SCORE LOCAL ---
                        local_score = calculate_local_frustration_score(entry.title, clean_content)
                        
                        if local_score < local_threshold:
                            # Le post n'exprime pas assez de friction ou est trop court :
                            # On passe au suivant SANS appeler l'API de Gemini (Économie de Quota)
                            continue
                        
                        print(f"  └─ 🔥 Match Fort Local [Score: {local_score} pts] : '{entry.title[:45]}...'")
                        print("     [IA] Évaluation sémantique et génération de solution...")
                        
                        # --- ÉTAPE OPTIMISATION 2 : TEMPORISATION SÉCURISÉE ---
                        time.sleep(query_delay)
                        
                        analysis = evaluate_post_with_ai_retry(
                            title=entry.title,
                            content=clean_content,
                            subreddit=sub_name,
                            url=entry.link,
                            opt_config=opt
                        )
                        
                        if analysis:
                            soi_score = analysis.get("soi", 0)
                            if soi_score >= config["min_soi_threshold"]:
                                print(f"     ⭐ IDÉE VALIDÉE ! [SOI: {soi_score}] -> {analysis['title_fr']}")
                                
                                validated_opportunity = {
                                    "id": post_id,
                                    "title": analysis["title_fr"],
                                    "source": f"Reddit - r/{sub_name}",
                                    "rawQuote": clean_content[:300] + ("..." if len(clean_content) > 300 else ""),
                                    "category": analysis["category"],
                                    "gravity": analysis["gravity"],
                                    "frequency": analysis["frequency"],
                                    "resolution": analysis["resolution_ease"],
                                    "accessibility": analysis["accessibility"],
                                    "soi": soi_score,
                                    "context": analysis["summary_fr"],
                                    "proposedSolution": analysis["proposed_solution_fr"],
                                    "targetCommunity": f"r/{sub_name}",
                                    "url": entry.link,
                                    "detected_at": datetime.now().strftime('%Y-%m-%d %H:%M')
                                }
                                
                                database.append(validated_opportunity)
                                known_ids.add(post_id)
                                new_discoveries += 1
                                
                                # Sauvegarde incrémentale
                                save_database(database)
                            else:
                                print(f"     [-] Filtré : Score SOI ({soi_score}) insuffisant.")
                        else:
                            print("     [-] Filtré : Rejeté par l'IA (Bruit ou non réalisable).")
                
                # Petite pause polie entre chaque requête de flux RSS
                time.sleep(1.5)
                
            except Exception as e:
                print(f"[!] Erreur de scraping RSS sur r/{sub_name} avec le mot-clé '{kw}' : {e}")
                continue
                
    print("\n" + "=" * 70)
    print("BILAN DE L'EXÉCUTION OPTIMISÉE")
    print(f"[+] Nouvelles opportunités validées et importées : {new_discoveries}")
    print(f"[+] Total d'opportunités en base : {len(database)}")
    print("=" * 70)

if __name__ == "__main__":
    run_pipeline()