from collections import defaultdict, Counter
from itertools import chain, permutations, product
import csv
import argparse

from tqdm import tqdm


def main(args):
    # Open datasets
    print(f'Reading champions file: {args.champions}')
    with open(args.champions, 'r') as f:
        reader = csv.DictReader(f)
        champions = {int(champion['key']):champion for champion in tqdm(reader)}
    print(f'We have {len(champions)} champions')

    # Read matches data
    print(f'Reading matches file: {args.matches}')
    with open(args.matches, 'r') as f:
        reader = csv.DictReader(f)
        matches = [row for row in tqdm(reader)]
    print(f'We have {len(matches)//10} matches, which will give {len(matches)} rows')

    # Partition matches by champions
    print(f'Partitioning matches by champions')
    matches_by_champion_picks = defaultdict(list)
    matches_by_champion_bans = defaultdict(list)
    for match in tqdm(matches):
        matches_by_champion_picks[int(match['championId_Pick'])].append(match)
        matches_by_champion_bans[int(match['championId_Ban'])].append(match)

    # Calculate bunch of rates
    total_games = len(matches) // 10
    for champion_id, champion in champions.items():
        # Select rows
        pick_rows = matches_by_champion_picks[champion_id]
        win_rows = [match for match in pick_rows if match['win_x'] == 'Win']
        ban_rows = matches_by_champion_bans[champion_id]

        # Calculate rates
        win_rate = len(win_rows) / len(pick_rows)
        pick_rate = len(pick_rows) / total_games
        ban_rate = len(ban_rows) / total_games
        pick_ban_rate = pick_rate + ban_rate

        # Calculate kda
        kda = calculate_kda(sum(int(row['kills']) for row in pick_rows), sum(int(row['deaths']) for row in pick_rows), sum(int(row['deaths']) for row in pick_rows))

        # Calculate win_rates over time
        total_bins = Counter(categorize(int(game['gameDuration'])) for game in pick_rows)
        win_bins = Counter(categorize(int(game['gameDuration'])) for game in win_rows)

        # Store champion stats
        champion['win_rate'] = win_rate
        champion['pick_rate'] = pick_rate
        champion['ban_rate'] = ban_rate
        champion['pick_ban_rate'] = pick_ban_rate
        champion['average_KDA'] = kda
        for duration in durations:
            champion[f'duration{duration}_total'] = total_bins[duration]
            champion[f'duration{duration}_wins'] = win_bins[duration]
            champion[f'duration{duration}_winrate'] = win_bins[duration] / total_bins[duration]


    # Group by gameid
    print('Grouping by gameid...')
    win_games = defaultdict(list) # {gameid: [champid1, champid2, ..., champid5]}
    lose_games = defaultdict(list) # {gameid: [champid1, champid2, ..., champid5]}
    for match in tqdm(matches):
        gameid = match['gameId']
        champ_pick = int(match['championId_Pick'])
        if match['win_x'] == 'Win':
            win_games[gameid].append(champ_pick)
        else:
            lose_games[gameid].append(champ_pick)

    # conditional_win_count_allies is a dictionary structured like {me: {allies: cnt}}
    # where conditional_win_count_allies[my_champ][ally_champ] = # of win matches done with my_champ and ally_champ
    conditional_win_count_allies = defaultdict(lambda: defaultdict(int))
    for _champions in win_games.values():
        for my_champ, ally_champ in permutations(_champions, 2):
            conditional_win_count_allies[my_champ][ally_champ] += 1

    # conditional_count_allies is a dictionary structured like {me: {allies: cnt}}
    # where conditional_count_allies[my_champ][ally_champ] = # of matches done with my_champ and ally_champ
    conditional_count_allies = defaultdict(lambda: defaultdict(int))
    for _champions in chain(win_games.values(), lose_games.values()):
        for my_champ, ally_champ in permutations(_champions, 2):
            conditional_count_allies[my_champ][ally_champ] += 1

    # conditional_win_count_counter is a dictionary structured like {me: {opponent: cnt}}
    conditional_win_count_counter = defaultdict(lambda: defaultdict(int))
    conditional_count_counter = defaultdict(lambda: defaultdict(int))
    for game_id, ally_champions in win_games.items():
        opponent_champions = lose_games[game_id]
        for my_champ, opponent_champ in product(ally_champions, opponent_champions):
            conditional_win_count_counter[my_champ][opponent_champ] += 1
            conditional_count_counter[my_champ][opponent_champ] += 1 # win-lose
    
    # win-lose / lose-win
    for game_id, ally_champions in lose_games.items():
        opponent_champions = win_games[game_id]
        for my_champ, opponent_champ in product(ally_champions, opponent_champions):
            conditional_count_counter[my_champ][opponent_champ] += 1 # lose-win


    # Calculate conditional win_rate over allied champions
    sample_threshold = 10
    top_k = 3
    for champion_id, champion in champions.items():
        # Given champion_id is yourself, 
        # dictionary of {ally_champion_id: win_rate}
        win_rates = {} 
        for ally_champion_id in champions.keys():
            # Skip yourself - yourself -> This will not happen
            if champion_id == ally_champion_id:
                continue
            numerator = conditional_win_count_allies[champion_id][ally_champion_id]
            denominator = conditional_count_allies[champion_id][ally_champion_id]
            # If there are not enough samples, ignore and dont calculate win rate
            if denominator < sample_threshold:
                print(f'We dont have enough data for champion: {champions[champion_id]["name"]} given ally: {champions[ally_champion_id]["name"]}')
            else:
                win_rates[ally_champion_id] =  numerator / denominator
        
        top_k_win_rate_champions = sorted(win_rates, key=win_rates.get, reverse=True)[:top_k] # lists champion ids by descending order of win_rates
        print(f'{[champions[c]["name"] for c in top_k_win_rate_champions]} champions are good with {champion["name"]}')
        for i in range(top_k):
            champion[f'Allies{i}'] = top_k_win_rate_champions[i]
            champion[f'Allies{i}_winrate'] = win_rates[top_k_win_rate_champions[i]]
            champion[f'Allies{i}_samples'] = denominator

    # Calculate conditional win_rate over opponent champions
    bottom_k = 3
    for champion_id, champion in champions.items():
        # Given champion_id is yourself, 
        # dictionary of {opponent_champion_id: win_rate}
        win_rates = {} 
        for opponent_champion_id in champions.keys():
            # Skip yourself - yourself -> This will not happen
            if champion_id == opponent_champion_id:
                continue
            numerator = conditional_win_count_counter[champion_id][opponent_champion_id]
            denominator = conditional_count_counter[champion_id][opponent_champion_id]
            if denominator < sample_threshold:
                print(f'We dont have enough data for champion: {champions[champion_id]["name"]} given opponent: {champions[opponent_champion_id]["name"]}')
            else:
                win_rates[opponent_champion_id] = numerator / denominator
        
        bottom_k_win_rate_champions = sorted(win_rates, key=win_rates.get)[:bottom_k] # lists champion ids by ascending order of win_rates
        print(f'{[champions[c]["name"] for c in bottom_k_win_rate_champions]} champions counters {champion["name"]}')
        for i in range(bottom_k):
            champion[f'Counters{i}'] = bottom_k_win_rate_champions[i]
            champion[f'Counters{i}_winrate'] = win_rates[bottom_k_win_rate_champions[i]]
            champion[f'Counters{i}_samples'] = denominator


    # Partition matches by 
    # Sort by win rate
    # -> need allies info
    # -> need dict of counts where me: {allies: cnt}
    # -> need dict of win_counts where me: {allies: win_count} 
    # -> need to group rows by games
    # -> dict of gameid: {{set of champions win}, {set of champions lost}}

    # Save results
    with open('Ultimate_champions_dataset.csv', 'w') as output:
        writer = csv.DictWriter(output, fieldnames=champions[266].keys())
        writer.writeheader()
        for champion in champions.values():
            writer.writerow(champion)



def calculate_kda(k, d, a):
    if d == 0:
        return k + a
    return (k + a) / d


durations = ['0-20', '20-25', '25-30', '30-35', '35+']
def categorize(seconds):
    if seconds <= 20 * 60:
        return '0-20'
    elif seconds <= 25 * 60:
        return '20-25'
    elif seconds <= 30 * 60:
        return '25-30'
    elif seconds <= 35 * 60:
        return '30-35'
    else:
        return '35+'



# Usage: 
# python main.py --champions Datasets/champions-updated.csv --matches merged_match_dataset_V2.csv
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-processing script to calculate interesting statistics")
    parser.add_argument('--champions', type=str, required=True, help='champions dataset')
    parser.add_argument('--matches', type=str, required=True, help="matches dataset")
    args = parser.parse_args()
    main(args)