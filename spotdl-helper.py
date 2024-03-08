from functools import lru_cache
from yt_dlp import YoutubeDL
import simplejson as json
import pandas as pd
import subprocess
import sys
import os

### Default values ###

ISSUES_URL = 'https://github.com/ArcWandx86/spotdl-helper/issues'
CWD = os.getcwd()

RULES = {
    'MODE': 'new',
    'URL': '',
    'DIFF-MODE': 'new',
    'DIFF-NEW': '',
    'DIFF-OLD': '',
    'OUTPUT-FORMAT': '{title} - {artists}',
    'DIR': './songs',
    'MP3GAIN': True,
    'IGNORE-MISMATCH': [],
    'REPLACE': [],
    'RENAME': [],
    'MANUAL-BUFFER': './.tmp_manual',
    'VERIFY-LEVEL': 6,
    'VERIFY-IGNORE-MISSING-URL': 3,

    # Skip options to resume an interrupted download
    'SKIP': 0,
    'BUFFER': './.tmp_dlbuf',
    'JSON-BUFFER': './.tmp_json',
}

SPOTIFY_TRACK_URL_PREFIX = 'https://open.spotify.com/track/'

# Delimiter used for parsing. Change this value to avoid conflicts
DELIMITER = '%,,'

## Rule types ##

# Note that rules are mutually exlusive; any rule should only fall under one category
TAKES_BOOL = set(['MP3GAIN'])
TAKES_INT = set(['VERIFY-LEVEL', 'VERIFY-IGNORE-MISSING-URL', 'SKIP'])
TAKES_FILE = {
    'new': [],
    'diff': ['DIFF-NEW', 'DIFF-OLD']
}
TAKES_DIR = {
    'new': ['DIR', 'MANUAL-BUFFER', 'BUFFER', 'JSON-BUFFER'],
    'diff': [],
}

# Rule : set([options])
TAKES_STR = {
    'MODE': set(['diff', 'new']),
    'DIFF-MODE': set(['new', 'old', 'diff', 'common']),
    'SKIP_TO': '',
}

# Rule : (checking function, error descriptor)
TAKES_ARRAY = {
    'IGNORE-MISMATCH': (lambda s: SPOTIFY_TRACK_URL_PREFIX in s, "must be Spotify url"),
    'REPLACE': (lambda s: '|' in s, "must contain '|'"),
    'RENAME': (lambda s: ':' in s, "must contain ':'"),
}

### \Default values ###


### Main ###

def main():
    filename = 'helper.rules'
    if len(sys.argv) > 1:
        filename = sys.argv[1]

    parser(filename, RULES)

    if RULES['MODE'] == 'diff':
        diff(RULES['DIFF-MODE'], RULES['DIFF-NEW'], RULES['DIFF-OLD'])
        return

    # Note that because all function arguments are set immediately after parsing,
    # modifying RULES will not affect the function calls
    # [ (func, [ params ]), ]
    funcs = [
        (download_songs, [ RULES['URL'], RULES['BUFFER'] ]),
        (manual_relace_songs, [ RULES['REPLACE'] ]),
        (download_metadata, [ RULES['JSON-BUFFER'] ]),
        (verify, [ RULES['VERIFY-LEVEL'], RULES['IGNORE-MISMATCH'] ]),
        (remove_ids, [ RULES['BUFFER'] ]),
        (rename, [ RULES['BUFFER'], RULES['MANUAL-BUFFER'], RULES['RENAME'] ]),
        (combine_and_clean, [ RULES['DIR'], RULES['BUFFER'], RULES['MANUAL-BUFFER'], RULES['JSON-BUFFER'] ]),
        (mp3gain, [ RULES['MP3GAIN'], RULES['DIR'] ]),
    ]

    # Executes the functions in func
    # Done this way to implement SKIP
    list(map(lambda z: z[0](*z[1]), funcs[RULES['SKIP']:]))

### \Main ###


### Helper ###

# Wrapper function for creating directories
def mkdir(dir):
    print(f'filesystem: mkdir {dir}')
    if not os.path.isdir(dir):
        os.makedirs(dir)
    else:
        print(f'FileWarning: {dir} already exists. No change')

# Wrapper function for removing directories
def rmdir(dir):
    print(f'filesystem: rmdir {dir}')
    if os.path.isdir(dir):
        os.rmdir(dir)
    else:
        print(f'FileWarning: {dir} does not exist. No change')

# Wrapper function for removing files
def rm(file):
    print(f'filesystem: rm {file}')
    if os.path.isfile(file):
        os.remove(file)
    else:
        print(f'FileWarning: {file} does not exist. No change')

# Wrapper function for renaming or moving files
def mv(old, new):
    print(f'filesystem: mv {old} {new}')
    if os.path.isfile(old):
        os.rename(old, new)
    else:
        print(f'FileWarning: {old} does not exist. No change')

# Helper function to call spotdl
def spotdl(dir, *args):
    os.chdir(CWD)
    os.chdir(dir)
    try:
        subprocess.run(['spotdl', *args])
    except FileNotFoundError:
        print('Error: spotdl not found. Is spotdl installed?')
        exit(1)
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
        if rule in TAKES_FILE[rules['MODE']]:
            errors += file_check(rule, setting)
        elif rule in TAKES_DIR[rules['MODE']]:
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

        # Replace the last comma on each line with special delimiter
        rules_file[i:j+1] = [ s.rsplit(',', 1)[0] + DELIMITER for s in rules_file[i:j+1] ]

        setting += ' '.join(['', *rules_file[i+1:j+1]])
        setting = setting.replace('[', '').replace(']', '').split(DELIMITER)
        setting = [s.strip() for s in setting if s.strip() != '']

        # Remove the lines we just processed
        rules_file[i:j+1] = [''] * (j-i+1)

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
        mkdir(setting)
    # Make sure the directory is empty
    if len(os.listdir(setting)) > 0:
        # If skip is non-zero, prompt to proceed
        if int(RULES['SKIP']) > 0:
            print(f'Warning: {setting} is not empty.')
            print('Press enter to continue...')
            input()
        else:
            return f'Error: {setting} is not empty.\n'
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
            return f'Error: {rule} {TAKES_ARRAY[rule][1]}.\nFailed on: {s}\n'
    return ''

### \Parsing ###


### Download songs ###

# Download songs into a buffer
def download_songs(url, buffer):
    if len(os.listdir(buffer)) > 0:
        print(f'Error: {buffer} is not empty.')
        exit(1)
    spotdl(buffer, '--output', RULES['OUTPUT-FORMAT']+'.{track-id}', url)

### \Download songs ###


### Manual replace songs ###

# Replaces songs based on the configuration array
def manual_relace_songs(replace_list):
    # Check that the buffer is clear
    if len(os.listdir(RULES['MANUAL-BUFFER'])) > 0:
        print(f'Error: {RULES["MANUAL-BUFFER"]} is not empty.')
        exit(1)

    # Split the list into spotify ids and the corresponding youtube urls
    spotids = { s.split('|')[1].strip().replace(SPOTIFY_TRACK_URL_PREFIX, '')
               .split('?')[0].strip() :
               s.split('|')[0].strip() for s in replace_list }

    replace_songs(spotids)

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
                rm(os.path.join(RULES['BUFFER'], file))

### \Manual replace songs ###


### Download metadata ###

# Use yt-dlp to download the metadata of the songs in the buffer
def download_metadata(json_buffer):
    # { filename: (title, artist, album, url)}
    metadata = get_ffprobe_data()
    fileurls = { file: data[3] for file, data in metadata.items() }

    with YoutubeDL() as ydl:
        i = 1
        for filename, url in fileurls.items():
            if url == '': handle_missing_url(filename)
            print(f'Downloading metadata for ({i}/{len(fileurls)})')
            i += 1

            # write to file
            with open(os.path.join(json_buffer, filename + '.json'), 'w') as f:
                f.write(json.dumps(ydl.sanitize_info(
                    ydl.extract_info(url, download=False))))

# Get the metadata of the songs in the buffer using ffprobe
# { filename: (title, artist, album, url)}
@lru_cache(maxsize=1)
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

def handle_missing_url(filename):
    match RULES['VERIFY-IGNORE-MISSING-URL']:
        case 0: # Error on missing url
            print(f'Error: {filename} has no url data.')
            print('Consider copying the output of spotdl to a text file for viewing.')
            exit(1)
        case 1: # Skip over missing url
            pass
        case 2: # Allow manual skipping of missing url
            print(f'Error: {filename} has no url data.')
            print('Please enter a url for the song.')
            url = input('Url: ')
            if url == '':
                print('WARNING: No url entered. Skipping song.')
        case 3: # (default) Ask for user input on missing url
            print(f'Error: {filename} has no url.')
            print('Please enter a url for the song.')
            url = input('Url: ')
            if url == '':
                print('Error: No url entered.')
                exit(1)
        case _:
            print(f'Error: Invalid value for VERIFY-IGNORE-MISSING-URL: {RULES["VERIFY-IGNORE-MISSING-URL"]}')

### \Download metadata ###


### Verification ###

# Verify that the correct songs were downloaded
def verify(level, ignore_mismatch):
    if level == 0:
        return

    ignore_mismatch = [s.replace(SPOTIFY_TRACK_URL_PREFIX, '') for s in ignore_mismatch]

    # { filename: (title, artist, album, url)}
    metadata = get_ffprobe_data()
    # { filename: (title, creator, channel, album)}
    yt_metadata = get_yt_data()

    # Make sure that title and artist match
    verification_queue = []
    for file, data in zip(metadata.keys(), metadata.values()):
        if queue_for_verification(level, file, data, yt_metadata[file], ignore_mismatch):
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

# Get the metadata of the songs in the buffer from the downloaded json
# { filename: (title, creator, channel, album)}
def get_yt_data():
    metadata = {}

    # extract metadata
    for file in os.listdir(RULES['JSON-BUFFER']):
        if not file.endswith('.json'): continue
        with open(os.path.join(RULES['JSON-BUFFER'], file), 'r') as f:
            data = json.load(f)
            title, creator, channel, album = '', '', '', ''
            if 'title' in data:
                title = data['title']
            if 'creator' in data:
                creator = data['creator']
            if 'channel' in data:
                channel = data['channel']
            if 'album' in data:
                album = data['album']

            filename = '.'.join(file.split('.')[:-1])
            metadata[filename] = (title, creator, channel, album)

    return metadata

# Check if the file should be queued for verification
def queue_for_verification(level, file, metadata, yt_metadata, ignore_mismatch):
    if '.'.join(file.split('.')[:-2]) in ignore_mismatch:
        return False

    title, artist, album, url = metadata
    yt_title, yt_creator, yt_channel, yt_album = yt_metadata

    match level:
        case 1:
            return title != yt_title or (artist != yt_creator and artist != yt_channel)
        case 2:
            return title != yt_title or (artist != yt_creator and artist != yt_channel) or album != yt_album
        case 3:
            return title != yt_title or (artist != yt_creator and artist != yt_channel) and not url.startswith('https://music.youtube.com/')
        case 4:
            return title != yt_title or (artist != yt_creator and artist != yt_channel) or album != yt_album or not url.startswith('https://music.youtube.com/')
        case 5:
            return title != yt_title or (artist != yt_creator and artist != yt_channel and album != yt_album)
        case 6:
            return (title != yt_title and f'{title} ({title})' != yt_title) or (artist != yt_creator and artist != yt_channel and album != yt_album)
        case _:
            print(f'Invalid verification level: {level}')
            exit(4)

# Prompt the user to verify the songs
def verification_prompt(queue, metadata, yt_metadata, ignore_mismatch):
    new_yt_urls = {}

    print()
    print()
    print(f'{len(queue)} song(s) may need verification.')
    for file in queue:
        title, artist, album, url = metadata[file]
        yt_title, yt_creator, yt_channel, yt_album = yt_metadata[file]
        print()
        print(f'{file}: {url}')
        print('Spotify: ')
        print(f'  Title: {title}')
        print(f'  Artist: {artist}')
        print(f'  Album: {album}')
        print('YouTube: ')
        print(f'  Title: {yt_title}')
        print(f'  Creator: {yt_creator}')
        print(f'  Channel: {yt_channel}')
        print(f'  Album: {yt_album}')
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
                    print(f'Search for {title} - {artist} on YouTube: https://www.youtube.com/results?search_query={title.replace(" ", "+")}+{artist.replace(" ", "+")}')
                    url = input('Enter a correct URL: ')
                    if url.startswith('https://') and 'youtu' in url:
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

### \Verification ###


### Remove IDs ###

# Remove IDs from the files in the buffer
def remove_ids(buffer):
    for file in os.listdir(buffer):
        if len(file.split('.')) < 3:
            continue
        mv(os.path.join(buffer, file),
           os.path.join(buffer, '.'.join(file.split('.')[:-2]) + '.' + file.split('.')[-1]))

### \Remove IDs ###


### Rename ###

def rename(buffer, manual_buffer, rename_list):
    # Split rename_list into rename_map
    rename_map = { name.split(':')[0].strip(): name.split(':')[1].strip() for name in rename_list }

    # { old_name : new_name }
    new_renames = rename_non_ascii(buffer, manual_buffer, rename_map)

    # Automatic rename remaining
    for file in os.listdir(buffer):
        if file in rename_map:
            mv(os.path.join(buffer, file), os.path.join(buffer, rename_map[file]))
    for file in os.listdir(manual_buffer):
        if file in rename_map:
            mv(os.path.join(manual_buffer, file), os.path.join(manual_buffer, rename_map[file]))

    # Give opportunity to copy the rename list
    if len(new_renames) > 0:
        print()
        print('=' * 80)
        print()
        print('You may want to copy the following array to helper.rules')
        print('RENAME=[') # ] to fix syntax highlighting
        for old_name, new_name in new_renames.items():
            print(f'    {old_name} : {new_name},')
        print(']')
        input('Press enter to continue...')

# Rename files with non-ASCII characters to be more easily searchable
def rename_non_ascii(buffer, manual_buffer, rename_map):
    rename_buffer = [ file for file in os.listdir(buffer) if any(ord(char) > 127 for char in file) ]
    rename_manual_buffer = [ file for file in os.listdir(manual_buffer) if any(ord(char) > 127 for char in file) ]
    new_renames = {}
    
    for file in rename_buffer:
        name = ''
        if file in rename_map:
            name = rename_map[file]
        else:
            name = rename_prompt(file)
            new_renames[file] = name
        mv(os.path.join(buffer, file), os.path.join(buffer, name))
    for file in rename_manual_buffer:
        name = ''
        if file in rename_map:
            name = rename_map[file]
        else:
            name = rename_prompt(file)
            new_renames[file] = name
        mv(os.path.join(manual_buffer, file), os.path.join(manual_buffer, name))

    return new_renames

# Prompt to get the new name
def rename_prompt(file):
    print()
    print(f'Non-ASCII characters found in {file}.')
    print('1. Ignore')
    print('2. Change only the title')
    print('3. Rename but keep file extension')
    print('4. Rename and change file extension')
    i = 0
    while True:
        i = input('Choose an option: ')
        try:
            i = int(i)
        except ValueError:
            print('Please enter a valid option.')
            continue
        if i >= 1 and i <= 4:
            break
        else:
            print('Please enter a valid option.')

    match i:
        case 1:
            return file
        case 2:
            return str(input('Enter a new title: ')) + ' - ' + file.split(' - ')[-1]
        case 3:
            return str(input('Enter a new name: ')) + '.' + file.split('.')[-1]
        case 4:
            return str(input('Enter a new name: '))
        case _:
            return file

### \Rename ###


### Combine and clean ###

# Combine the directories and remove the buffers
def combine_and_clean(dir, buffer, manual_buffer, json_buffer):
    os.chdir(CWD)

    # Move everything to dir
    for file in os.listdir(buffer):
        mv(f'{buffer}/{file}', f'{dir}/{file}')
    for file in os.listdir(manual_buffer):
        mv(f'{manual_buffer}/{file}', f'{dir}/{file}')

    # Remove the buffers
    if dir != buffer:
        rmdir(buffer)
    if dir != manual_buffer:
        rmdir(manual_buffer)

    # Remove all json metadata
    for file in os.listdir(json_buffer):
        if file.endswith('.json'):
            rm(f'{json_buffer}/{file}')
    if dir != json_buffer:
        rmdir(json_buffer)

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


### Diff ###

def diff(mode, new, old):
    new = pd.read_csv(new)
    old = pd.read_csv(old)

    # Extract IDs
    new_ids = set(new['Track URI'])
    old_ids = set(old['Track URI'])

    # Find the diff
    match mode:
        case 'new': diff = new_ids - old_ids
        case 'old': diff = old_ids - new_ids
        case 'diff': diff = new_ids ^ old_ids
        case 'common': diff = new_ids & old_ids
        case _:
            print(f'Invalid diff mode: {mode}')
            exit(3)

    print('Spotify ID,Title,Artist,Album,URL')
    for id in diff:
        new_row = new.loc[new['Track URI'] == id]
        old_row = old.loc[old['Track URI'] == id]
        match mode:
            case 'new': row = new_row
            case 'old': row = old_row
            case 'diff': row = new_row if len(new_row) > 0 else old_row
            case 'common': row = new_row
            case _:
                print(f'Invalid diff mode: {mode}')
                exit(3)

        row = row.iloc[0]
        print(f'{row["Track URI"]}, {row["Track Name"]}, {row["Artist Name(s)"]}, {row["Album Name"]}')

### \Diff ###


if __name__ == '__main__':
    main()
