import pandas as pd
import time
from datetime import datetime

def preprocess(df, mapping_equipe):
    """
    Cette fonction effectue plusieurs opérations de prétraitement sur nos données footballistiques scrappées.
    
    :param df: DataFrame contenant les données footballistiques.
    :param mapping_equipe: Dictionnaire pour la normalisation des noms des équipes.
    :param mean_cols: Colonnes pour lesquelles calculer les moyennes roulantes.
    :param outcome_cols: Colonnes pour lesquelles calculer les statistiques cumulatives des résultats des matchs.
    :param lag_cols: Colonnes pour lesquelles appliquer des décalages (lags).
    """

    # Conversion et nettoyage des colonnes 'Date' et 'Time' en une seule colonne
    df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
    df.drop(["Date", "Time"], axis=1, inplace=True)
    df = df[['DateTime'] + [col for col in df if col != 'DateTime']]

    # Normalisation des noms des équipes pour qu'il n'y est pas de noms de mêmes équipes différentes
    df['Opponent'] = df['Opponent'].map(mapping_equipe).fillna(df['Opponent'])
    df['equipe'] = df['equipe'].map(mapping_equipe).fillna(df['equipe'])

    # Garder que les matchs 'Ligue 1' (pas de matchs de Coupe)
    df = df[df["Comp"] == "Ligue 1"]

    # Extraire uniquement le numéro de chaque journée (en ligue 1 il y'a 38 journées par an, ici on ne garde que le numéro)
    df['Round'] = df['Round'].str.extract(r'(\d+)').astype(int)

    # Création d'une colonne "Saison" qui nous permettra de facilement accéder au matchs d'une année partiulière
    df['Saison'] = df['DateTime'].apply(lambda x: f"{x.year}-{x.year + 1}" if x.month >= 8 else f"{x.year - 1}-{x.year}")
    
    # Création de la variable de différence entre buts marqués et encaissés
    df[['GF', 'GA']] = df[['GF', 'GA']].astype(float).astype(int)
    df['GD'] = df['GF'] - df['GA']

    # Création d'une colonne "Points" pour chaque match joués
    df['Points'] = df['Result'].map({'W': 3, 'D': 1, 'L': 0})

    # Calcul cumulatif des Points, des buts marqués/encaissés et de la différence de buts par saison
    df.sort_values(by=['Saison', 'Round', 'equipe'], inplace=True)
    df.reset_index(drop=True, inplace=True)

    cumulative_cols = df.groupby(['Saison', 'equipe']).agg({
        'Points': 'cumsum',
        'GD': 'cumsum',
        'GF': 'cumsum',
        'GA': 'cumsum'
    }).reset_index()

    df[['Points_Cum', 'GD_Cum', 'GF_Cum', 'GA_Cum']] = cumulative_cols[['Points', 'GD', 'GF', 'GA']]

    # Nettoyage de la colonne 'Formation'
    df['Formation'] = df['Formation'].str.replace('◆', '')

    # Calculer un classement basé sur les points cumulés et la différence de buts
    df.sort_values(by=['Saison', 'Round', 'Points_Cum', 'GD_Cum'], ascending=[True, True, False, False], inplace=True)
    df['Classement'] = df.groupby(['Saison', 'Round']).cumcount() + 1

    """ # Application des décalages (lags)
    df[[f'{col}_Lag1' for col in lag_cols]] = df.groupby(['Saison', 'equipe'])[lag_cols].shift(1)


    # Calcul des moyennes roulantes
    for col in mean_cols:
        df[f'Moyenne_{col}'] = df.groupby(['Saison', 'equipe'])[col].transform(lambda x: x.shift(1).expanding().mean())
    """

    # Création d'un identifiant unique pour analyser les dernières rencontres entre deux équipes

    outcome_cols = ['IsWin', 'IsDraw', 'IsLoss']
    df['MatchID'] = df['equipe'] + '_' + df['Opponent']
    df['Past_Matches'] = df.groupby('MatchID').cumcount()
    df['IsWin'] = df['Result'].apply(lambda x: 1 if x == 'W' else 0)
    df['IsDraw'] = df['Result'].apply(lambda x: 1 if x == 'D' else 0)
    df['IsLoss'] = df['Result'].apply(lambda x: 1 if x == 'L' else 0)
    df[['CumulativeWins', 'CumulativeDraws', 'CumulativeLosses']] = df.groupby('MatchID')[outcome_cols].cumsum()

    # Réorganisez les colonnes dans le DataFrame
    colonnes_a_afficher_en_premier = ["DateTime", "Comp", "Round", "Day", "Venue", "equipe", "Classement",  
                                  "Formation", "Result", "GF", "GA", "Opponent", "Past_Matches", 
                                  "CumulativeWins", "CumulativeDraws", "CumulativeLosses", 
                                  "Attendance", "Captain", "Referee"]
    # Réorganisez les colonnes dans le DataFrame
    #df = df[colonnes_a_afficher_en_premier + [col for col in df.columns if col not in colonnes_a_afficher_en_premier]]
   
    nouvelles_colonnes = colonnes_a_afficher_en_premier + [col for col in df.columns if col not in colonnes_a_afficher_en_premier]
    df = df[nouvelles_colonnes]
    # Réinitialisation de l'index et tri final
    df.reset_index(drop=True, inplace=True)
    df.sort_values(by=['Saison', 'equipe', 'DateTime'], inplace=True)

    return df

#mean_cols = ['Standard_SoT%', 'Total_Cmp%', 'Poss_x', 'Touches_Def Pen', 'Touches_Def 3rd']
#outcome_cols = ['IsWin', 'IsDraw', 'IsLoss']
#lag_cols = ['Points_Cum', 'GD_Cum', 'GF_Cum', 'GA_Cum']


def add_new_matches(base_initiale, base_nouvelle):

    # Le scrapping change l'odre des colonnes il faut donc les réaligner pour concaténer
    base_nouvelle = base_nouvelle[base_initiale.columns]

    # Concaténation des deux bases de données et suppression des doublons
    concatenated_data = pd.concat([base_nouvelle, base_initiale]).drop_duplicates().sort_values(by ="DateTime").reset_index(drop=True)

    return concatenated_data


def preparation_model(df):

    """ Une fois le preprocess utilisé sur la base, on prépare la base pour modéliser de la prédiction
    pour cela on créer des variables laggés, des variables par saisons, et des variables dont on aurait accès avant un match
    """

    # 0. Préparation pour le calcul cumulatif
    df.sort_values(by=['Saison', 'Round', 'equipe'], inplace=True)
    df.reset_index(drop=True, inplace=True)

    # 1. Application des décalages (lags) sur les variables principales

    lag_cols = ['Points_Cum', 'GD_Cum', 'GF_Cum', 'GA_Cum']
    df[[f'{col}_Lag1' for col in lag_cols]] = df.groupby(['Saison', 'equipe'])[lag_cols].shift(1)
    
    # 2. Création du classement et des cumulatives laggés des dernières rencontres entre les deux équipes
    df['Classement_Lag1'] = df.groupby(['equipe'])['Classement'].shift(1)

    df[['CumulativeWins_Lag1', 'CumulativeDraws_Lag1', 'CumulativeLosses_Lag1']] = df.groupby('MatchID')[['CumulativeWins', 'CumulativeDraws', 'CumulativeLosses']].shift(1)


    # 3. Liste des colonnes de statistiques pour lesquelles calculer les moyennes mobiles décalées
    stat_columns = [
        col for col in df.columns 
        if col.startswith(('Standard_', 'Expected_', 'Poss_', 'Touches_', 'Take-Ons_', 'Carries_', 
                       'Receiving_', 'Tackles_', 'Challenges_', 'Blocks_', 'Total_', 'Short_', 
                       'Medium_', 'Long_', 'Performance_', 'Penalty Kicks_', 'Launched_', 
                       'Passes_', 'Goal Kicks_', 'Crosses_', 'Sweeper_'))
    ]

    for col in stat_columns:
        df[f'Moyenne_{col}_Lag'] = df.groupby(['Saison', 'equipe'])[col].transform(lambda x: x.shift(1).expanding().mean())

    # Suppression des colonnes initiales de statistiques pour éviter les fuites de données (data leakage)
    df.drop(stat_columns, axis=1, inplace=True, errors='ignore')

    # Réorganisation finale du DataFrame
    df = df.sort_values(by=['Saison', 'equipe', 'DateTime']).reset_index(drop=True)
    

    return df
