# mbmc: MusicBrainz Metadata Collector

## Installing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
pip install -e .
```

 - Add credentials to `.env` file for Spotify and Tidal.

## How to use

1. Add an artist, Add as many external links as you can find.
2. Start the script with the artist url as argument.

```bash
python -m mbmc <artist_url>
```

### General flow

 - You will be asked for each album if the album found with the provider matches it.
 - Select a matching one via 1-9.
 - If you selected any album, you will be asked if it matches any known Musicbrainz releases.

### Amending a release

 - A new edit will be opened to add all missing urls to the existing record
 - The only thing currently being added are external links to streaming providers

### Adding a new release

You will be prompted for additional confirmation. If you ignore any prompt, the release will not be added.

Each prompt will only be shown if there is more than one possibility, and answers will be saved for future questions
(mainly relevant for artist selection).

 - Select the release name
 - Track layout (how many disks, how many tracks per disk)
   - If any selected album has a different number of tracks than selected here, it will be discarded. You should add it
     as separate release
 - Track lengths (including ms, if available)
 - Track titles
 - Album artist
 - Release date
 - Barcode
 - Release Type
 - Release Language
 - Track artists

Once all questions have been answered, a add release form is automatically opened in the browser,
prefilled with all details selected earlier. This is meant to be a template to ease some of the
repetitive tasks. You are explicitly invited to make changes, if applicable. The tool wil try to
have sensible defaults, but it will not cover all cases.

#### Artist selection

When prompted to select an artist, there will be multiple Possibilities:

 - [Artist] Artist that has been matched to a Musicbrainz artist automatically
 - {Artist} Artist that was not found on Musicbrainz
 - everything else will be join phrases (like `, ` or ` feat. `)

## Banning albums

If you decide to ban an album, the top most album from the current search results will be banned.
This is useful, if a streaming service mixes up multiple real artists into one artist page, and you expect to run the
program again in the future (i.e. to add new releases).

Banning will only ban that particular artist-album combination (artist being identified by mbid, and album by url), so
you will still see the banned album for other artists (useful for featured tracks).
