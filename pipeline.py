#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pipeline d'Idéation RSS Standardisé et Évolutif (Sans API Reddit)
------------------------------------------------------------------
Ce script utilise les flux RSS publics de Reddit. Il ne nécessite aucun
compte développeur Reddit, aucune clé API Reddit et contourne la politique
"Responsible Builder Policy" de manière totalement transparente.
"""

import os
import json
import time
import re
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Literal, Optional, List
from dotenv import load_dotenv
import requests
import feedparser
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Charger la variable confidentielle du fichier .env
load_dotenv()

# =====================================================================
# MODÈLE DE DONNÉES ET INTERFACES (CONTRATS DE STANDARDISATION)
# =====================================================================

class FrustrationAnalysis(BaseModel):
    """Schéma de validation strict pour l'IA (Structured Output)."""
    is_valid_pain: bool = Field(
        description="True si le texte exprime une frustration exploitable pour créer un produit ou service. False sinon."
    )
    title_fr: str = Field(
        description="Titre du problème traduit ou rédigé de manière concise en français."
    )
    category: Literal["Micro-SaaS", "Objet Physique", "Hybride (HW/SW)"] = Field(
        description="Type de solution le plus adapté au problème."
    )
    gravity: int = Field(
        description="Note de 1 à 10 de la douleur ou de la perte générée."
    )
    frequency: int = Field(
        description="Note de 1 à 10 de la récurrence du problème."
    )
    resolution_ease: int = Field(
        description="Note de 1 à 10 décrivant la facilité à concevoir un MVP."
    )
    accessibility: int = Field(
        description="Note de 1 à 10 décrivant la facilité à distribuer la solution dans ce canal."
    )
    summary_fr: str = Field(
        description="Description détaillée de la frustration rédigée en français."
    )
    target_persona: str = Field(
        description="Profil type de l'utilisateur souffrant du problème (en français)."
    )


class BaseScraper(ABC):
    """Interface standard pour toutes les sources de données."""
    
    @abstractmethod
    def fetch_recent_posts(self, config: dict) -> List[dict]:
        """Doit retourner une liste de dictionnaires standardisés."""
        pass


class BaseLLMService(ABC):
    """Interface standard pour les services d'IA."""
    
    @abstractmethod
    def evaluate_frustration(self, title: str, content: str, source: str) -> Optional[dict]:
        """Doit analyser le texte et renvoyer une fiche d'opportunité unifiée ou None."""
        pass

# =====================================================================
# IMPLÉMENTATION DES SOURCES : SCRAPER RSS REDDIT (SANS API REDDIT !)
# =====================================================================

class RedditRSSScraper(BaseScraper):
    """Scraper standard utilisant les flux RSS publics (contourne l'API)."""
    
    def __init__(self):
        # Utiliser un User-Agent de navigateur classique pour éviter les blocages de sécurité
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
    def _clean_html(self, raw_html: str) -> str:
        """Supprime les balises HTML contenues dans les résumés des flux RSS."""
        cleanr = re.compile('<.*?>')
        text = re.sub(cleanr, ' ', raw_html)
        # Nettoyer les mentions répétitives de l'auteur
        text = re.sub(r'submitted by.*?\s', '', text)
        return " ".join(text.split())
        
    def fetch_recent_posts(self, config: dict) -> List[dict]:
        raw_items = []
        subreddits = config.get("subreddits", [])
        keywords = config.get("trigger_keywords", [])
        
        for sub_name in subreddits:
            try:
                # Récupération du flux RSS "new" du subreddit
                url = f"https://www.reddit.com/r/{sub_name}/new.rss"
                response = requests.get(url, headers=self.headers, timeout=10)
                
                if response.status_code == 200:
                    feed = feedparser.parse(response.text)
                    print(f"[Scraper] Analyse de r/{sub_name} ({len(feed.entries)} posts trouvés)")
                    
                    for entry in feed.entries:
                        content_clean = self._clean_html(entry.get("summary", ""))
                        text_to_check = (entry.title + " " + content_clean).lower()
                        has_keyword = any(kw in text_to_check for kw in keywords)
                        
                        if has_keyword:
                            # Extraction de l'ID du post depuis l'URL (ex: 'comments/18a7b9c/title')
                            post_id = entry.link.split("/")[-3] if "comments" in entry.link else entry.id
                            
                            raw_items.append({
                                "id": f"reddit-{post_id}",
                                "raw_id": post_id,
                                "title": entry.title,
                                "content": content_clean,
                                "platform": "Reddit (RSS)",
                                "source_community": f"r/{sub_name}",
                                "url": entry.link
                            })
                else:
                    print(f"[Scraper] Code {response.status_code} sur r/{sub_name} (Accès bloqué ou subreddit inexistant)")
            except Exception as e:
                print(f"[Scraper] Erreur de lecture sur r/{sub_name} : {e}")
                
            # Temporisation polie pour éviter de surcharger les serveurs de Reddit
            time.sleep(1.5)
                
        return raw_items

# =====================================================================
# IMPLÉMENTATION DES LLM : SERVICE GOOGLE GEMINI
# =====================================================================

class GeminiLLMService(BaseLLMService):
    """Implémentation standard utilisant l'API Gemini."""
    
    def __init__(self, model_name: str):
        # Initialise le client. Récupère automatiquement GEMINI_API_KEY
        self.client = genai.Client()
        self.model_name = model_name
        
    def evaluate_frustration(self, title: str, content: str, source: str) -> Optional[dict]:
        system_instruction = (
            "Tu es un agent d'étude de marché multilingue d'élite. Ton but est d'analyser un texte "
            "et de déterminer s'il exprime une véritable frustration exploitable pour créer un produit "
            "ou un service (SaaS, physique ou hybride).\n\n"
            "DIRECTIVE CRUCIALE DE TRADUCTION :\n"
            "Peu importe la langue d'origine (anglais, espagnol, français), tu devez obligatoirement "
            "générer les champs 'title_fr' et 'summary_fr' en FRANÇAIS correct et fluide.\n\n"
            "Si le texte n'exprime pas une frustration claire et exploitable, renvoie is_valid_pain = false."
        )
        
        prompt = f"""
        Source / Communauté d'origine : {source}
        Titre d'origine : {title}
        Contenu d'origine : {content}
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=FrustrationAnalysis,
                    temperature=0.15
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[LLM] Erreur d'analyse sémantique : {e}")
            return None

# =====================================================================
# LE CONTROLEUR PRINCIPAL DU PIPELINE (ORCHESTRATEUR)
# =====================================================================

class PipelineController:
    """Orchestre la collecte RSS, l'évaluation IA et l'archivage."""
    
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
            
        self.db_path = "detected_frustrations.json"
        self.database = self.load_database()
        
        llm_provider = self.config.get("active_llm_provider", "gemini")
        model_name = self.config.get("active_llm_model", "gemini-2.5-flash")
        
        if llm_provider == "gemini":
            self.llm_service = GeminiLLMService(model_name)
        else:
            raise ValueError(f"Le fournisseur d'IA '{llm_provider}' n'est pas encore configuré.")
            
    def load_database(self) -> list:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []
        
    def save_database(self):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.database, f, indent=2, ensure_ascii=False)
            
    def calculate_soi(self, gravity, frequency, resolution, accessibility):
        """Calcul du Score SOI (Score d'Opportunité d'Idéation)."""
        divisor = 11 - resolution
        if divisor <= 0:
            divisor = 1
        return round((gravity * frequency * accessibility) / divisor)

    def run(self):
        print("=" * 70)
        print(f"Lancement du pipeline RSS : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        
        known_ids = {item["id"] for item in self.database}
        new_discoveries = 0
        
        if "reddit_rss" in self.config["sources"]:
            print("[Pipeline] Initialisation du collecteur RSS Reddit...")
            scraper = RedditRSSScraper()
            rss_config = self.config["sources"]["reddit_rss"]
            
            print("[Pipeline] Collecte en cours sur les flux RSS publics...")
            raw_posts = scraper.fetch_recent_posts(rss_config)
            print(f"[Pipeline] {len(raw_posts)} posts pré-sélectionnés pour l'analyse IA.")
            
            for post in raw_posts:
                if post["id"] in known_ids:
                    continue
                
                print(f"\n  └─ Évaluation de '{post['title'][:40]}...' ({post['source_community']})")
                
                # Respecter le quota gratuit Gemini (15 req/min max = ~4.5s de pause)
                time.sleep(4.5)
                
                analysis = self.llm_service.evaluate_frustration(
                    title=post["title"],
                    content=post["content"],
                    source=post["source_community"]
                )
                
                if analysis and analysis.get("is_valid_pain"):
                    soi_score = self.calculate_soi(
                        analysis["gravity"],
                        analysis["frequency"],
                        analysis["resolution_ease"],
                        analysis["accessibility"]
                    )
                    
                    if soi_score >= self.config["min_soi_threshold"]:
                        print(f"     ⭐ IDÉATION VALIDÉE ! [SOI: {soi_score}] - {analysis['title_fr']}")
                        
                        validated_opportunity = {
                            "id": post["id"],
                            "title": analysis["title_fr"],
                            "source": f"{post['platform']} - {post['source_community']}",
                            "rawQuote": post["content"][:300] + ("..." if len(post["content"]) > 300 else ""),
                            "category": analysis["category"],
                            "gravity": analysis["gravity"],
                            "frequency": analysis["frequency"],
                            "resolution": analysis["resolution_ease"],
                            "accessibility": analysis["accessibility"],
                            "soi": soi_score,
                            "context": analysis["summary_fr"],
                            "targetCommunity": post["source_community"],
                            "url": post["url"],
                            "detected_at": datetime.now().strftime('%Y-%m-%d %H:%M')
                        }
                        
                        self.database.append(validated_opportunity)
                        known_ids.add(post["id"])
                        new_discoveries += 1
                        
                        # Sauvegarde immédiate
                        self.save_database()
                    else:
                        print(f"     [-] Filtré : Score SOI ({soi_score}) inférieur au seuil.")
                else:
                    print("     [-] Filtré : Pas d'opportunité identifiée.")
                    
        print("\n" + "=" * 70)
        print(f"[Bilan] Fin d'exécution.")
        print(f"[+] Nouvelles opportunités importées : {new_discoveries}")
        print(f"[+] Total d'opportunités en base : {len(self.database)}")
        print("=" * 70)


if __name__ == "__main__":
    controller = PipelineController()
    controller.run()