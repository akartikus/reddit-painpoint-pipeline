# PainPoint AI : Pipeline d'Idéation de Business Automatisé (Quota-Safe & Multilingue)

PainPoint AI est un agent autonome d'écoute et d'étude de marché multilingue (FR/EN/ES). Il scanne les subreddits publics via les flux RSS de recherche de Reddit (sans clé API Reddit), pré-filtre localement le bruit pour économiser vos quotas d'IA, valide sémantiquement les frictions réelles avec Google Gemini, puis calcule un score d'opportunité d'idéation ($SOI$) et exporte des fiches de projets prêtes à l'emploi.

Cette approche permet de concevoir des projets (Micro-SaaS, objets physiques ou produits hybrides) en partant de frustrations réelles, de besoins déjà exprimés par des utilisateurs existants, avec un canal de distribution intégré.

 ## 1. Architecture Globale du Pipeline

Le code est conçu de manière modulaire et standardisée (découplée). Le traitement intègre un double rempart pour protéger vos quotas d'appels API Gemini et garantir un coût de fonctionnement de 0 €.

       +-------------------------------------------------------+
       |                     config.json                       |
       +-------------------------------------------------------+
                                   | (Configure le pipeline & quotas)
                                   v
                      +--------------------------+
                      |    PipelineController    | <---+ (Chef d'orchestre)
                      +--------------------------+     |
                                   |                   |
               +-------------------+-------------------+
               |                                       |
               v                                       v
      [  BaseScraper  ]                       [ BaseLLMService ] (Interfaces standards)
               |                                       |
               | (implémente)                          | (implémente)
               v                                       v
      +------------------+                    +------------------+
      | RedditRSSScraper |                    | GeminiLLMService | (Classes concrètes)
      +------------------+                    +------------------+
               |                                       |
               | (Analyse RSS historique)              | (Gère Rate-Limit & Erreur 429)
               v                                       v
         [ Post Brut ]                         +---------------------+
               |                               | FrustrationAnalysis | (Schéma de sortie strict)
               |                               +---------------------+
               v                                       |
       +-------------------------------------------------------+
       |               detected_frustrations.json              | (Base de données unifiée)
       +-------------------------------------------------------+

## 2. Le Voyage d'une Frustration & Sécurisation des Quotas

Pour éviter de saturer l'API gratuite de Gemini (limite de 15 requêtes/minute), le pipeline implémente un entonnoir de filtrage strict :


 [ Étape 1 : Collecte RSS Anonyme ]
   Scan temporel via RSS Search sur les subreddits cibles (r/productivity, r/pedale, r/es...).
     │
     ▼
 [ Étape 2 : Pré-filtrage Local (0 token IA utilisé) ] ◄── ÉCONOMISE ~85% DES APPELS API
   Algorithme local de calcul de friction (poids sur les mots-clés, longueur minimale, etc.).
   Le post dépasse-t-il le score local requis (ex: 25 pts) ?
     │
     ├── [ NON ] ──► Ignoré localement de façon instantanée et gratuite.
     │
     └── [ OUI ]
           │
           ▼
 [ Étape 3 : Régulation Temporelle Strict (Throttling) ] ◄── SÉCURITÉ DE DÉBIT
   Le script applique une temporisation stricte (ex: 5.0s d'attente) entre chaque requête.
     │
     ▼
 [ Étape 4 : Analyse sémantique par l'IA (Gemini-2.5-flash) ]
   Validation stricte de faisabilité technique/matérielle pour un solopreneur.
     │
     ├── [ Erreur 429 / Quota dépassé ] ──► Backoff exponentiel (pause & réessai intelligent).
     │
     ├── [ is_valid_pain = False ] ──► Rejeté (C'est un mème, une question théorique, du spam).
     │
     └── [ is_valid_pain = True ]
           │
           ▼ (Traduction forcée en français, synthèse & génération de MVP)
           │
 [ Étape 5 : Calcul du Score d'Opportunité d'Idéation (SOI) ]
   Calcul mathématique automatique. Passage au crible du seuil de filtrage final (ex: SOI >= 75).
     │
     ▼
 [ Étape 6 : Stockage & Visualisation ]
   Sauvegarde dans "detected_frustrations.json" ──► Visualisable sur PainPoint AI Viewer !

## 3. Les Formules Mathématiques de Tri

### A. Algorithme de Friction Local (Pré-filtrage Python)

Avant d'interroger Gemini, le script attribue des points à la volée aux textes bruts :

Mots-clés de forte friction (ex: manually, hate doing this, galère, comment automatiser) : de $+10$ à $+25$ points.

Pénalité de longueur : Les textes de moins de 15 mots subissent une pénalité de $-15$ points (manque de contexte pour l'IA).

Bonus argumentatif : $+5$ points pour les posts constructifs (entre 30 et 250 mots).

### B. Le Score d'Opportunité d'Idéation ($SOI$)

Une fois validée par Gemini, l'opportunité est notée de $1$ à $10$ sur 4 variables par l'IA :

Gravité ($G$) : Intensité de la douleur (ex: perte d'argent = $10$, simple clic superflu = $2$).

Fréquence ($F$) : Récurrence de la frustration (ex: quotidiennement = $10$, annuel = $1$).

Facilité de Résolution ($R$) : Simplicité technique à concevoir un MVP (facile à faire = $10$, R&D complexe = $1$).

Accessibilité du Canal ($C$) : Facilité de distribution organique dans le subreddit (très ouvert = $10$).

Le score final est déterminé par la formule :

$$SOI = \frac{G \times F \times C}{11 - R}$$

Plus le score $SOI$ est élevé (généralement $> 75$), plus le projet résout un problème douloureux, récurrent, facile à concevoir et à distribuer.

## 4. Personnalisation et Configuration (config.json)

Vous pouvez piloter tout le comportement de l'agent sans modifier le code de calcul via config.json :

{
  "subreddits": ["productivity", "pedale", "es"],
  "trigger_keywords": ["alternative to", "manuellement", "molesto"],
  "min_soi_threshold": 75,
  "optimization": {
    "max_queries_per_minute": 12,
    "delay_between_queries_seconds": 5.0,
    "local_prefilter_score_threshold": 25,
    "gemini_retry_attempts": 3,
    "gemini_retry_delay_seconds": 10
  }
}


delay_between_queries_seconds : Temps d'attente forcé entre chaque appel à l'IA (en secondes).

local_prefilter_score_threshold : Seuil minimal de points au pré-filtrage Python pour mériter un appel Gemini.

gemini_retry_attempts : Nombre d'essais en cas d'erreur de quota (HTTP 429).

gemini_retry_delay_seconds : Pause initiale de sécurité avant réessai (doublée à chaque échec).

 ## 5. Installation Rapide

Installez les paquets requis :

pip install google-genai python-dotenv requests feedparser


Créez votre fichier .env :

GEMINI_API_KEY=votre_cle_gemini_gratuite


Exécutez l'agent autonome :

python pipeline.py


Ouvrez viewer.html et déposez-y votre fichier detected_frustrations.json mis à jour pour analyser graphiquement vos nouvelles idées d'affaires !
