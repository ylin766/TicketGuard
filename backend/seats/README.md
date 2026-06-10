# Seats Workflow

After the price scraper creates its JSON file, run:

```bash
python backend/seats/match_tickets.py \
  backend/features/price/stubhub_seats.json \
  -o matched.csv
```

`match_tickets.py` reads `metadata.venue` and every ticket's `section`, matches
them against `backend/seats/seats-data/photos_avfms`, and writes `matched.csv`.

The CSV field is `photo_urls`, not a local path. Multiple images are separated
with ` | `.

Start the seats image server so the frontend can open those URLs:

```bash
python backend/seats/serve_images.py
```

The default URL format is:

```text
http://localhost:8001/photos_avfms/mercedes_benz_stadium/section217-1.jpg
```

For a deployed image server, generate the CSV with its public URL:

```bash
python backend/seats/match_tickets.py \
  price.json \
  -o matched.csv \
  --image-base-url https://api.example.com/seat-images
```
