# Data
မူရင်းဖိုင်ကို raw.folder တွင်ထည့်ပေးထားသည်။ (data/raw)။ heading များပြင်ဆင်ပြီး ဒီမှာပဲ .md ဖြင့် သိမ်းသည်။

# 1. clean_text.py ဖြင့် clean-bom&white-space ဖယ်သည်။ 

# 2. chunk_split.py ဖြင့် chunk ဖိုင် 4 ဖိုင်ခွဲသည်။

# 3. md_headings_parse.py ဖြင့် headinf ထည့်ထားသော .md ဖိုင်ကို စာကြောင်းတစ်ကြောင်းချင်း မှန်ကန်အောင် ပြုပြင်သည်။

# 4. join_headings_by_tokens.py chunk ခွဲထားသောဖိုင်နှင့် heading ပြင်ဆင်ထားသော ဖိုင်ကို ပေါင်းသည်။

# 5. make_labse_embeddings.py ဖြင့် vector ပြောင်းသည်။

>python etl/app/pipeline2.py ကို cmd မှာ run လိုက်လျှင် vector ပြောင်းပြီး အဆင့်အထိ ရပါမည်။