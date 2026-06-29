I believe we can create some E2E/Benchmark test

This is AI harness for if we stablish our philosophy maybe we can measure somehow the impact of our changes. And automate the improvement validations.

Idea here is we stole already existing repositories. And we create our test repository. Before each PR approval this will run some kind of test that implies changes over repository.

We cant test some imposible ideas over this test repos and see if detects bullshit.

We can test how good implements easy fixes. 

We can test how good implements good fixes.

We can test how good it collects learning.

We can test how good do almost everything.

We can start by one confiable measure and maybe implement the others progresively.

We need or real existing tools int the market that allows check our code in a valid comparable way. Like code complexity, no security bugs, lines of code... something that allows to say "this is better code than the other".

If for some reason we end needing IA to solve this then we need to maintain scores out of scope of the IA. Else the pipeline can cheat the scores. Needs to be some external mechanism isolated that calculates this.

Mayor problem of this E2E test: It cost tokens so it cost money. Would be wonderful if we find a way to avoid this. Maybe need some free model support more than claude/codex.


----

Sí. Para una suite E2E de harness de código, miraría estas opciones:

1. Groq: probablemente la mejor para tests rápidos. Tiene tier gratis sin tarjeta, con rate limits; sirve para CI/prototipos, no producción pesada.

2. OpenRouter Free Models: muy práctico si quieres probar varios modelos con una API tipo OpenAI. Tiene modelos gratis, normalmente con límites diarios/minuto.

3. Gemini API Free Tier: buena opción general, especialmente modelos Flash/Flash-Lite; Google mantiene free tier, pero límites y modelos cambian.

4. Local con Ollama/vLLM: “gratis” en tokens si tienes máquina/GPU. Para E2E determinista suele ser lo mejor: usas Qwen/Coder, Llama, DeepSeek Coder, etc., sin coste por llamada.

---

1. Tests del harness
Usa modelo local/mock. Valida:

parsing
tool calls
retries
streaming
schema JSON
errores
timeouts
snapshots
control de prompts

Aquí no importa si el modelo es “listo”; importa que el sistema aguante.

2. Tests de comportamiento barato
Usa modelos cloud gratis/baratos tipo Groq, OpenRouter :free, o Gemini Flash. OpenRouter documenta 20 rpm y 50 requests/día en free, o 1000/día si compras al menos $10 en créditos.

3. Tests de calidad real
Pocos casos contra el modelo objetivo: GPT/Claude/Gemini Pro, etc. Solo smoke tests o golden tests críticos.

La estrategia más justa sería:

PR:
  mock/local → 100% suite

nightly:
  modelo barato cloud → subset amplio

release:
  modelo target caro → 10-30 casos críticos

Y sí: para “parche fácil”, un local sirve. Para medir si tu agente realmente programa bien, no. Ahí necesitas el modelo cloud real, aunque sea con una muestra pequeña.