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
    'MP3GAIN': True,
    'IGNORE-MISMATCH': [],
    'REPLACE': [],
    'MANUAL-BUFFER': './tmp_manual',
    'DUP-SCAN-LEVEL': 3,
    'VERIFY-LEVEL': 1,

    # Skip options to resume an interrupted download
    'SKIP': 0,
    'BUFFER': './tmp_dlbuf',
}

SPOTIFY_TRACK_URL_PREFIX = 'https://open.spotify.com/track/'

## Rule types ##

TAKES_BOOL = set(['MP3GAIN'])
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
    'IGNORE-MISMATCH': (lambda s: SPOTIFY_TRACK_URL_PREFIX in s, "must Spotify url"),
    'REPLACE': (lambda s: '|' in s, "must contain '|'"),
}

### \Default values ###


### Helper ###

# Helper function to call spotdl
def spotdl(dir, *args):
    os.chdir(CWD)
    os.chdir(dir)
    subprocess.run(['spotdl', *args])
    os.chdir(CWD)

### \Helper ###

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
        elif rule in TAKES_BOOL:
            e = bool_check(rule, setting)
            if e == '':
                rules[rule] = str(setting).lower() in ['true', '1', 't', 'y', 'yes']
            else:
                errors += e
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

def bool_check(rule, setting):
    if str(setting).lower() in ['true', '1', 't', 'y', 'yes', 'false', '0', 'f', 'n', 'no']:
        return ''
    return f'Error: {rule} must be a boolean.\n'

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

# Download songs into a buffer
def download_songs(url, buffer):
    for file in os.listdir(buffer):
        os.remove(os.path.join(buffer, file))
    spotdl(buffer, '--output', RULES['OUTPUT-FORMAT']+'.{track-id}', url)

### \Download songs ###


### Manual replace songs ###

# Replace songs by their spotify id with a given youtube url
def replace_songs(spotids):
    # Download the replacements into a separate buffer
    for spotid, url in spotids.items():
        spotdl(RULES['MANUAL-BUFFER'], '--output', RULES['OUTPUT-FORMAT'],
               url + '|' + SPOTIFY_TRACK_URL_PREFIX + spotid)
        # Delete the replaced song from the main buffer
        for file in os.listdir(RULES['BUFFER']):
            if len(file.split('.')) < 3:
                continue
            if file.split('.')[-2] == spotid:
                os.remove(os.path.join(RULES['BUFFER'], file))

# Replaces songs based on the configuration array
def manual_relace_songs(replace_list):
    # Clear the buffer
    for file in os.listdir(RULES['MANUAL-BUFFER']):
        os.remove(os.path.join(RULES['MANUAL-BUFFER'], file))

    # Split the list into spotify ids and the corresponding youtube urls
    spotids = { s.split('|')[1].strip().replace(SPOTIFY_TRACK_URL_PREFIX, '')
               .split('?')[0].strip() :
               s.split('|')[0].strip() for s in replace_list }

    replace_songs(spotids)

### \Manual replace songs ###


### Remove IDs ###

# Remove IDs from the files in the buffer
def remove_ids(buffer):
    for file in os.listdir(buffer):
        if len(file.split('.')) < 3:
            continue
        os.rename(os.path.join(buffer, file),
                  os.path.join(buffer, '.'.join(file.split('.')[:-2]) + '.' + file.split('.')[-1]))

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

# Prompt the user to verify the songs
def verification_prompt(queue, metadata, yt_metadata, ignore_mismatch):
    new_yt_urls = {}

    print()
    print()
    print(f'{len(queue)} song(s) may need verification.')
    for file in queue:
        print()
        print(f'{file}: {metadata[file][3]}')
        print('Spotify: ')
        print(f'  Title: {metadata[file][0]}')
        print(f'  Artist: {metadata[file][1]}')
        print(f'  Album: {metadata[file][2]}')
        print('YouTube: ')
        print(f'  Title: {yt_metadata[file][0]}')
        print(f'  Creator: {yt_metadata[file][1]}')
        print(f'  Channel: {yt_metadata[file][2]}')
        print(f'  Album: {yt_metadata[file][3]}')
        print()

        if file.split('.')[-2] in ignore_mismatch:
            print('Ignoring mismatch.')
            continue

        while True:
            response = input('Do these match? [y/n] ').lower()
            if response == 'y':
                if len(file.split('.')) < 3:
                    print(f'File {file} is improperly formatted.')
                    exit(6)
                ignore_mismatch.append(file.split('.')[-2])
                break
            elif response == 'n':
                while True:
                    url = input('Enter a correct URL: ')
                    if url.startswith('https://') and 'youtube' in url:
                        if len(file.split('.')) < 3:
                            print(f'File {file} is improperly formatted.')
                            exit(6)
                        new_yt_urls[file.split('.')[-2]] = url
                        break
                    else:
                        print('Please enter a valid YouTube URL.')
                break
            else:
                print('Please enter y or n.')
        print()

    return new_yt_urls, ignore_mismatch

# Verify that the correct songs were downloaded
def verify(level, ignore_mismatch):
    if level == 0:
        return

    ignore_mismatch = [s.replace(SPOTIFY_TRACK_URL_PREFIX, '') for s in ignore_mismatch]

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

    # Prompt the user to verify the songs
    if len(verification_queue) == 0:
        return

    # { spotify_id: youtube_url }
    new_yt_urls, ignore_mismatch = verification_prompt(verification_queue, metadata, yt_metadata, ignore_mismatch)
    if len(new_yt_urls) == 0 and len(ignore_mismatch) == 0:
        return

    # Give opportunity to copy the array
    print()
    print('=' * 80)
    print()
    print('You may want to copy the following array(s) to helper.rules')
    # Ignore mismatch
    if len(ignore_mismatch) > 0:
        print('IGNORE-MISMATCH=[') # ] to fix syntax highlighting
        for spotify_id in ignore_mismatch:
            print(f'    {SPOTIFY_TRACK_URL_PREFIX}{spotify_id},')
        print(']')

    # Replace
    if len(new_yt_urls) > 0:
        print('REPLACE=[') # ] to fix syntax highlighting
        for spotify_id, youtube_url in new_yt_urls.items():
            print(f'    {youtube_url} | {SPOTIFY_TRACK_URL_PREFIX}{spotify_id},')
        print(']')
    input('Press enter to continue...')

    replace_songs(new_yt_urls)

### \Verification ###


### Combine and clean ###

# Combine the directories and remove the buffers
def combine_and_clean(dir, buffer, manual_buffer):
    os.chdir(CWD)

    # Move everything to dir
    for file in os.listdir(buffer):
        os.rename(f'{buffer}/{file}', f'{dir}/{file}')
    for file in os.listdir(manual_buffer):
        os.rename(f'{manual_buffer}/{file}', f'{dir}/{file}')

    # Remove the buffers
    os.rmdir(buffer)
    os.rmdir(manual_buffer)

    os.chdir(CWD)

### \Combine and clean ###


### MP3GAIN ###

# Apply mp3gain
def mp3gain(yes, dir):
    if not yes:
        return

    os.chdir(CWD)
    os.chdir(dir)
    subprocess.run('mp3gain -r *', shell=True)
    os.chdir(CWD)

### \MP3GAIN ###


### Main ###

def main():
    filename = 'helper.rules'
    if len(sys.argv) > 1:
        filename = sys.argv[1]

    parser(filename, RULES)

    # [ (func, [ params ]), ]
    funcs = [
        (download_songs, [ RULES['URL'], RULES['BUFFER'] ]),
        (manual_relace_songs, [ RULES['REPLACE'] ]),
        (verify, [ RULES['VERIFY-LEVEL'], RULES['IGNORE-MISMATCH'] ]),
        (remove_ids, [ RULES['BUFFER'] ]),
        (duplicate_check, [ RULES['DUP-SCAN-LEVEL'] ]),
        (combine_and_clean, [ RULES['DIR'], RULES['BUFFER'], RULES['MANUAL-BUFFER'] ]),
        (mp3gain, [ RULES['MP3GAIN'], RULES['DIR'] ]),
    ]

    # Executes the functions in func
    # Done this way to implement SKIP
    list(map(lambda z: z[0](*z[1]), funcs[RULES['SKIP']:]))

### \Main ###


if __name__ == '__main__':
    main()
