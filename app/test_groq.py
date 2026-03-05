import os
from dotenv import load_dotenv
from openai import OpenAI
import time

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

print("🧪 Testeando Groq directo...")
start = time.time()

try:
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.7,
        max_tokens=400,
        messages=[
            {"role": "user", "content": "Hola"}
        ],
    )
    
    elapsed = time.time() - start
    print(f"✅ Respuesta en {elapsed:.2f}s")
    print(f"📝 Mensaje: {completion.choices[0].message.content}")
    
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ Error después de {elapsed:.2f}s")
    print(f"Error: {e}")