#  import pandas as pd
import subprocess
import sys
import os

### Default values ###

ISSUES_URL = 'https://github.com/ArcWandx86/spotdl-helper/issues'
CWD = os.getcwd()

RULES = {
    'MODE': 'new',
    'OUTPUT-FORMAT': '{title} - {artists}',
    'URL': '',
    'DIR': './songs',
    'REPLACE': [],
    'MANUAL-BUFFER': './tmp_manual',
    'DUP-SCAN-LEVEL': 3,
    'VERIFY-LEVEL': 1,

    # Skip options to resume an interrupted download
    'SKIP': 0,
    'BUFFER': './tmp_dlbuf',
}

## Rule types ##

TAKES_INT = set(['DUP-SCAN-LEVEL', 'VERIFY-LEVEL', 'SKIP'])
TAKES_FILE = set(['NEW', 'OLD'])

# Rule : set([ Modes to create if dir does not exist ])
TAKES_DIR = {
    'DIR' : set(['new']),
    'MANUAL-BUFFER' : set(['merge', 'new']),
    'BUFFER' : set(['merge', 'new']),
}

# Rule : set([options])
TAKES_STR = {
    'MODE': set(['merge', 'new']),
    'SKIP_TO': '',
}

# Rule : (checking function, error descriptor)
TAKES_ARRAY = {
    'REPLACE': (lambda s: '|' in s, "must contain '|'"),
}

### \Default values ###


### Parsing ###

# Sets the RULES dictionary
def parser(filename, rules):
    with open(filename, 'r') as f:
        rules_file = f.read()
    rules_file = rules_file.split('\n')

    errors = ''
    for i, line in enumerate(rules_file):
        line = line.strip()
        # ignore blank lines and commented lines
        if line == '' or line[0] == '#':
            continue

        rule, setting, errors, rules_file = get_setting(i, line, rules_file, errors)
        # Add line number
        rules[rule] = setting

    for rule, setting in rules.items():
        if rule in TAKES_FILE:
            errors += file_check(rule, setting)
        elif rule in TAKES_DIR:
            errors += directory_check(rule, setting)
        elif rule in TAKES_INT:
            e = int_check(rule, setting)
            if e == '':
                rules[rule] = int(setting)
            else:
                errors += e
        elif rule in TAKES_STR:
            errors += string_check(rule, setting)
        elif rule in TAKES_ARRAY:
            errors += array_check(rule, setting)

    # Handle errors
    if len(errors) > 0:
        print(errors, end='')
        exit(1)

def get_setting(i, line, rules_file, errors=''):
    # Split on the first equals sign
    rule = line.split('=', 1)[0].strip()
    if rule not in RULES:
        errors += f'Error: {rule} is not a valid rule. (line {i+1})\n'
        return rule, '', errors, rules_file
    setting = line.split('=', 1)[1].strip()
    if setting == '':
        return rule, RULES[rule], errors, rules_file

    # Parse array
    if setting.startswith('['): # ] formatter freaks out without this comment
        # Advance until we find the closing bracket
        j = i
        while j < len(rules_file):
            if ']' in rules_file[j]:
                break
            j += 1
        if j == len(rules_file):
            errors += f'Error: Missing closing bracket. (line {i+1})\n'
            return rule, '', errors, rules_file

        setting += ' '.join(['', *rules_file[i+1:j+1]])
        rules_file[i:j+1] = [''] * (j-i+1) # Remove the lines we just processed
        setting = setting.replace('[', '').replace(']', '').split(',')
        setting = [s.strip() for s in setting if s.strip() != '']

    return rule, setting, errors, rules_file

def file_check(rule, setting):
    if not isinstance(setting, str):
        return f'Error: {rule} must be a file name.\n'
    if not os.path.isfile(setting):
        return f'Error: "{setting}" not found for {rule}.\n'
    return ''

def directory_check(rule, setting):
    if not isinstance(setting, str):
        return f'Error: {rule} must be a directory name.\n'
    if not os.path.isdir(setting):
        # Make the directory if it doesn't exist
        if RULES['MODE'] in TAKES_DIR[rule]:
            os.makedirs(setting)
        else:
            return f'Error: "{setting}" not found for {rule}.\n'
    return ''

def int_check(rule, setting):
    # Try to make the setting an int
    try:
        setting = int(setting)
    except ValueError:
        return f'Error: {rule} must be an integer.\n'
    return ''

def string_check(rule, setting):
    if not isinstance(setting, str):
        return f'Error: {rule} must be a string.\n'
    if setting not in TAKES_STR[rule]:
        return f'Error: {rule} must be one of {TAKES_STR[rule]}.\n'
    return ''

def array_check(rule, setting):
    if not isinstance(setting, list):
        return f'Error: {rule} must be a list.\n'
    for s in setting:
        # Use the lambda in TAKES_ARRAY to check if the string is valid
        if not TAKES_ARRAY[rule][0](s):
            return f'Error: {rule} {TAKES_ARRAY[rule][1]}.\n'
    return ''

### \Parsing ###


### Download songs ###

# Helper function to call spotdl
def spotdl(dir, *args):
    os.chdir(CWD)
    os.chdir(dir)
    subprocess.run(['spotdl', *args])
    os.chdir(CWD)

# Download songs into a buffer
def download_songs(url, buffer):
    spotdl(buffer, '--output', RULES['OUTPUT-FORMAT']+'.{track-id}', url)

### \Download songs ###


### Manual replace songs ###

# Replaces songs based on a manually specified youtube url
def replace_songs(replace_list):
    spotify_track_url_prefix = 'https://open.spotify.com/track/'
    # Split the list into spotify ids and the corresponding youtube urls
    spotids = { s.split('|')[1].strip().replace(spotify_track_url_prefix, '')
               .split('?')[0].strip() :
               s.split('|')[0].strip() for s in replace_list }

    # Download the replacements into a separate buffer
    spotdl(RULES['MANUAL-BUFFER'], '--output', RULES['OUTPUT-FORMAT'],
           *[ url + '|' + spotify_track_url_prefix + spotid for spotid, url in spotids.items() ])

    # Delete the replaced songs from the main buffer
    for file in os.listdir(RULES['BUFFER']):
        if len(file.split('.')) < 2:
            continue
        if file.split('.')[-2] in spotids:
            os.remove(os.path.join(RULES['BUFFER'], file))

### Manual replace songs ###

### \Manual replace songs ###


### Main ###

def main():
    filename = 'helper.rules'
    if len(sys.argv) > 1:
        filename = sys.argv[1]

    parser(filename, RULES)

    funcs = [
        (download_songs, (RULES['URL'], RULES['BUFFER'])),
        (replace_songs, (RULES['REPLACE'],)),
    ]

    list(map(lambda z: z[0](*z[1]), funcs[RULES['SKIP']:]))

### \Main ###


if __name__ == '__main__':
    main()
