import gdown
url = "https://drive.google.com/drive/folders/1BMt0DRSEyp4OHA7qK0-3RPS2ofwCIKGN"
gdown.download_folder(url, output="outputs", quiet=False, use_cookies=False)
