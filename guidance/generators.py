import openai
import pathlib
import diskcache
import os
import time
import requests

curr_dir = pathlib.Path(__file__).parent.resolve()
_file_cache = diskcache.Cache(f"{curr_dir}/../lm.diskcache")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)

if OPENAI_API_KEY is None:
    try:
        with open(os.path.expanduser('~/.openai_api_key'), 'r') as file:
            openai.api_key = file.read().replace('\n', '')
    except:
        raise Exception("Warning: No OpenAI api key found, you need to set the OPENAI_API_KEY environment variable or put your key in the file ~/.openai_api_key")

try:
    with open(os.path.expanduser('~/.openai_lm_model_name'), 'r') as file:
        gpt_model = file.read().replace('\n', '')
except:
    raise Exception("Warning: No OpenAI model name found, you need to put your OpenAI model name in the file ~/.openai_lm_model_name")

class OpenAI():
    def __init__(self, model=None, caching=True, max_retries=2, token=None, endpoint=None):

        # default to environment variable values
        if model is None:
            model = os.environ.get("OPENAI_MODEL", gpt_model)
        if token is None:
            token = os.environ.get("OPENAI_API_KEY", None)
        if endpoint is None:
            endpoint = os.environ.get("OPENAI_ENDPOINT", None)
        
        self.model = model
        self.caching = caching
        self.max_retries = max_retries
        self.token = token
        self.endpoint = endpoint
    
    def __call__(self, prompt, stop=None, temperature=0.0, n=1, max_tokens=1000, logprobs=None, top_p=1.0):
        key = "_---_".join([str(v) for v in (self.model, prompt, stop, temperature, n, max_tokens, logprobs)])
        if key not in _file_cache or not self.caching:

            fail_count = 0
            while True:
                try_again = False
                try:
                    if self.endpoint is None:
                        caller = self._library_call
                    else:
                        caller = self._rest_call
                    out = caller(
                        model=self.model, prompt=prompt, max_tokens=max_tokens,
                        temperature=temperature, top_p=top_p, n=n, stop=stop, logprobs=logprobs#, stream=True
                    )

                except openai.error.RateLimitError:
                    time.sleep(3)
                    try_again = True
                    fail_count += 1
                
                if not try_again:
                    break

                if fail_count > self.max_retries:
                    raise Exception(f"Too many (more than {self.max_retries}) OpenAI API RateLimitError's in a row!")

            _file_cache[key] = out
        return _file_cache[key]

    def _library_call(self, **kwargs):
        return openai.Completion.create(**kwargs)

    def _rest_call(self, **kwargs):
        # Define the request headers
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }

        # Define the request data
        data = {
            "prompt": kwargs["prompt"],
            "max_tokens": kwargs["max_tokens"],
            "temperature": kwargs["temperature"],
            "top_p": kwargs["top_p"],
            "n": kwargs["n"],
            "stream": False,
            "logprobs": kwargs["logprobs"],
            'stop': kwargs["stop"]
        }

        # Send a POST request and get the response
        response = requests.post(self.endpoint, headers=headers, json=data)
        if response.status_code != 200:
            raise Exception("Response is not 200: " + response.text)
        return response.json()

    def tokenize(self, strings):
        out = openai.Completion.create(
            model=self.model, prompt=strings, max_tokens=1, temperature=0, logprobs=0, echo=True
        )
        return [choice["logprobs"]["tokens"][:-1] for choice in out["choices"]]