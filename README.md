# မြန်မာ usage cheat-sheet:

## Docker အရင်တင်

./bootstrap.sh up


## ETL အစိတ်အပိုင်းရွေးပြေး (သို့) အားလုံးပြေး

အားလုံး:

./bootstrap.sh etl
 သို့မဟုတ်
./bootstrap.sh all   # up → etl(full) → setup → load → search


## အပိုင်းရွေး (ဥပမာ cleaning+split+embed ပဲ):

./bootstrap.sh etl --steps clean,split,parse,join,embed


## outputs overwrite လိုရင်:

./bootstrap.sh etl --steps clean,split,parse,join,embed --force


## Weaviate side (placeholder hooks အကြောင်း)

./bootstrap.sh setup   # schema/collections
./bootstrap.sh load    # insert BM25 + vectors
./bootstrap.sh search  # sanity query


## အလုပ်လိုဂျစ် (ဖိုင်လမ်းကြောင်း/နာမည်တွေ သင်နောက်ဆုံးပြင်ထားသလိုထားတယ်):

RAW: data/raw/

CLEAN: data/outputs/cleaned_text/

SPLIT(per file): data/outputs/{stem}_chunk_split/

chunks.csv, subchunks_200.csv, sentences_from_200.csv, windows_2_3.csv

HEADING PARSE: data/outputs/{stem}_hd_parse/

JOIN: data/outputs/{stem}_join_headings_by_tokens/

*_with_headings.csv

EMBED: data/outputs/{stem}_labse_embeddings/

windows_labse.npy, windows_ids.txt … (placeholder သတ်မှတ်ထား — မင်းရဲ့ real embed script ချိတ်ဖို့ hook ပြင်ထားပြီး)

## ခေါင်းစဉ်အလိုက် steps ရှင်းလင်း:

clean  → raw → cleaned_text
split  → cleaned_text → *_chunk_split
parse  → .md headings → *_hd_parse
join   → split + headings → *_with_headings.csv
embed  → *_with_headings.csv (မရှိရင် split CSVs ကို fallback) → *_labse_embeddings
setup  → Weaviate schema/collections
load   → Insert CSV + vectors
search → Sanity query


### မှတ်ချက်: Embed/Weaviate steps သည် placeholder call တွေ ထားထားပေးထားသည်—မင်းရဲ့ make_labse_embeddings.py, create_schema.py, insert_data.py … စတဲ့ “အလုံးစုံ” script များကို အခု pipeline function တွေ (step_embed/step_setup_weaviate/step_load/step_search) ထဲမှာ import/call လုပ်ပေးရုံဖြင့် တစ်ခုတည်းထဲကနေ flow တစ်လျှောက် ချိတ်သွားနိုင်အောင် structure ပေးထားတယ်။