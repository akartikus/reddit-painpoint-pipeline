# PainPoint AI : Pipeline d'Idéation de Business Automatisé

PainPoint AI est un agent autonome d'écoute et d'étude de marché multilingue. Il scanne les forums publics (via les flux RSS de Reddit), pré-filtre le bruit, analyse sémantiquement les frictions réelles avec l'IA (Google Gemini), calcule un score d'opportunité d'idéation ($SOI$) et exporte des fiches de projets prêtes à l'emploi.

Cette approche permet de concevoir des projets (Micro-SaaS, objets physiques ou produits hybrides) en partant de frustrations réelles, de besoins déjà exprimés par des utilisateurs existants, avec un canal de distribution intégré.

## 1. Architecture du Pipeline (Qui fait quoi ?)

Le code est conçu de manière modulaire et standardisée (découplée). Les sources de données (Scrapers) et les moteurs d'intelligence artificielle (LLM Services) sont isolés derrière des contrats d'interfaces. Vous pouvez ajouter une source ou changer de modèle d'IA en modifiant simplement le fichier config.json.

       +-------------------------------------------------------+
       |                     config.json                       |
       +-------------------------------------------------------+
                                   | (Configure)
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
               | (Génère du texte brut)                | (Valide & Traduit)
               v                                       v
         [ Post Brut ]                         +---------------------+
               |                               | FrustrationAnalysis | (Schéma de sortie strict)
               |                               +---------------------+
               v                                       |
       +-------------------------------------------------------+
       |               detected_frustrations.json              | (Base de données unifiée)
       +-------------------------------------------------------+


### Rôle des composants clés :

PipelineController : Le chef d'orchestre. Il initialise les modules, gère l'historique pour éviter les doublons, calcule le score final et écrit le fichier de sortie.

BaseScraper : Interface standard de collecte. N'importe quel nouveau collecteur (ex: Amazon Reviews, Quora) doit l'implémenter.

RedditRSSScraper : Collecteur sans clé API. Il interroge anonymement les flux RSS publics des subreddits configurés et contourne proprement les barrières d'accès développeur de Reddit.

BaseLLMService : Interface standard d'analyse sémantique.

GeminiLLMService : Intègre l'API Gemini (gratuite en deçà de 15 requêtes/minute) pour lire, filtrer le bruit, catégoriser, et traduire systématiquement en français les problèmes détectés.

## 2. Le Voyage d'une Frustration (Flux de données)

Voici le cycle complet suivi par une plainte utilisateur sur Reddit avant d'atterrir sur votre Dashboard :

 [ Étape 1 : Collecte Anonyme ]
   Reddit RSS public (r/productivity, r/bikecommuting...)
     │
     ▼
 [ Étape 2 : Pré-filtrage rapide ]
   Recherche de mots-clés de friction dans le titre et le contenu :
   "alternative à", "galère", "manually", "hate doing this", "molesto"...
     │
     ├── [ Non trouvé ] ──► Ignoré (Gratuit, économise les tokens de l'IA)
     │
     └── [ Trouvé ]
           │
           ▼
 [ Étape 3 : Analyse sémantique par l'IA (Gemini-2.5-flash) ]
   L'IA évalue s'il s'agit d'une vraie frustration exploitable pour créer un produit.
     │
     ├── [is_valid_pain = False] ──► Rejeté (C'est un mème, de l'auto-promo ou du spam)
     │
     └── [is_valid_pain = True]
           │
           ▼ (Traduction forcée et synthèse des données en français)
           │
 [ Étape 4 : Calcul du Score d'Opportunité d'Idéation (SOI) ]
   Calcul mathématique automatique basé sur 4 curseurs (évalués de 1 à 10 par l'IA)
     │
     ▼
 [ Étape 5 : Filtrage par Seuil & Archivage ]
   Si SOI >= Seuil configuré (ex: 75) ──► Enregistré dans "detected_frustrations.json"
     │
     ▼
 [ Étape 6 : Visualisation ]
   Prêt à être affiché dans votre Dashboard React pour concevoir votre MVP !


## 3. La Formule Mathématique : Score SOI

Chaque frustration détectée est évaluée selon quatre variables notées de $1$ à $10$ :

Gravité ($G$) : Intensité de la douleur (ex: perte d'argent = $10$, simple clic superflu = $2$).

Fréquence ($F$) : Récurrence de la frustration (ex: quotidiennement = $10$, une fois par an = $1$).

Facilité de Résolution ($R$) : Simplicité technique pour concevoir un MVP (ex: facile à coder/fabriquer = $10$, recherche lourde = $1$).

Accessibilité du Canal ($C$) : Facilité à distribuer la solution dans cette communauté (ex: sous-forum hyper actif et ouvert = $10$).

Le Score d'Opportunité d'Idéation ($SOI$) est calculé de la manière suivante :

$$SOI = \frac{G \times F \times C}{11 - R}$$

Plus le score $SOI$ est élevé (généralement $> 80$), plus le projet résout un problème douloureux, récurrent, facile à concevoir et à distribuer de façon organique.
