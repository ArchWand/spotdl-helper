from yt_dlp import YoutubeDL
import simplejson as json
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
        if len(file.split('.')) < 3:
            continue
        if file.split('.')[-2] in spotids:
            os.remove(os.path.join(RULES['BUFFER'], file))

### \Manual replace songs ###


### Remove IDs ###

# Remove IDs from the files in the buffer
def remove_ids(buffer):
    for file in os.listdir(buffer):
        if len(file.split('.')) < 3:
            continue
        os.rename(os.path.join(buffer, file),
                  os.path.join(buffer, '.'.join(file.split('.')[:-1]) + '.' + file.split('.')[-1]))

### \Remove IDs ###


### Duplicate check ###

# Check for duplicates
def duplicate_check(level):
    if level == 0 or RULES['MODE'] != 'merge':
        return

    # Get the list of songs in the buffer
    buffer_songs = os.listdir(RULES['BUFFER'])
    # Get the list of songs in the output directory
    output_songs = set(os.listdir(RULES['OUTPUT']))

    # Get the list of songs that are in both the buffer and the output
    duplicates = [s for s in buffer_songs if s in output_songs]

    match level:
        case 1: # Delete the duplicates from the buffer
            for file in duplicates:
                os.remove(os.path.join(RULES['BUFFER'], file))
        case 2: # Delete the duplicates from the existing directory
            for file in duplicates:
                os.remove(os.path.join(RULES['OUTPUT'], file))
        case 3: # Manual review
            if len(duplicates) == 0:
                return

            with open('duplicates.txt', 'w') as f:
                f.write('\n'.join(duplicates))
            print(f'{len(duplicates)} duplicates found.\n')
            if len(duplicates) < 15:
                print('Duplicates:')
                print('\n'.join(duplicates))

            print('Duplicates written to duplicates.txt')
            print('Please remove the duplicates and run again.')
            exit(4)

### \Duplicate check ###


### Verification ###

# Get the metadata of the songs in the buffer using ffprobe
def get_ffprobe_data():
    metadata = {}

    # Download the metadata of the songs in the buffer
    ffprobe_cmd = ['ffprobe', '-v', '0', '-show_entries', 'format']
    
    for file in os.listdir(RULES['BUFFER']):
        title = ''
        artist = ''
        album = ''
        url = ''

        result = subprocess.run(ffprobe_cmd + [os.path.join(RULES['BUFFER'], file)], capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr)
            exit(5)

        for line in result.stdout.split('\n'):
            if line.startswith('TAG:title='):
                title = line.split('TAG:title=')[1]
            elif line.startswith('TAG:artist='):
                artist = line.split('TAG:artist=')[1]
            elif line.startswith('TAG:album='):
                album = line.split('TAG:album=')[1]
            elif line.startswith('TAG:comment=https://'):
                url = line.split('TAG:comment=')[1]

        metadata[file] = (title, artist, album, url)

    return metadata

# Get the metadata of the songs in the buffer using yt-dlp
def get_yt_data(fileurls):
    metadata = {}

    with YoutubeDL() as ydl:
        for filename, url in fileurls.items():
            data = json.loads(json.dumps(ydl.sanitize_info(
                ydl.extract_info(url, download=False))))

            title, creator, channel, album = '', '', '', ''
            try:
                title = data['title']
            except KeyError:
                pass
            try:
                creator = data['creator']
            except KeyError:
                pass
            try:
                channel = data['channel']
            except KeyError:
                pass
            try:
                album = data['album']
            except KeyError:
                pass

            metadata[filename] = (title, creator, channel, album)

    return metadata

# Verify that the correct songs were downloaded
def verify(level):
    if level == 0:
        return

    # { filename: (title, artist, album, url)}
    metadata = get_ffprobe_data()
    # { filename: (title, creator, channel, album)}
    yt_metadata = get_yt_data({ file: data[3] for file, data in metadata.items() })

    # Make sure that title and artist match
    verification_queue = []
    for file, (title, artist, album, _), _, (yt_title, creator, channel, yt_album) in zip(
        metadata.keys(), metadata.values(), yt_metadata.keys(), yt_metadata.values()):
        if title != yt_title:
            verification_queue.append(file)
        if artist != creator and artist != channel:
            verification_queue.append(file)
        if level == 2 or level == 4 and album != yt_album:
            verification_queue.append(file)

    print('Metadata: ')
    print(metadata)
    print('Youtube metadata: ')
    print(yt_metadata)
    print('Verification queue: ')
    print(verification_queue)

### \Verification ###


### Main ###

def main():
    filename = 'helper.rules'
    if len(sys.argv) > 1:
        filename = sys.argv[1]

    parser(filename, RULES)

    funcs = [
        (download_songs, [ RULES['URL'], RULES['BUFFER'] ]),
        (replace_songs, [ RULES['REPLACE'] ]),
        (remove_ids, [ RULES['BUFFER'] ]),
        (duplicate_check, [ RULES['DUP-SCAN-LEVEL'] ]),
        (verify, [ RULES['VERIFY-LEVEL'] ]),
    ]

    list(map(lambda z: z[0](*z[1]), funcs[RULES['SKIP']:]))

### \Main ###


if __name__ == '__main__':
    main()
