# Timeline — setup moderno (Python 3.11 + Docker)

Esta branch moderniza o Timeline 7.7 sem alterar de propósito o protocolo AS2/AS3 do CPPS.

> Estado: o core do servidor está portado diretamente para Python 3.11. Os handlers/plugins históricos que ainda estão em sintaxe Python 2 passam temporariamente por uma camada de compatibilidade `lib2to3` em memória. Essa camada é transitória e deverá desaparecer quando todos os módulos forem convertidos diretamente.

## Requisitos

- Git
- Docker Desktop / Docker Engine com Docker Compose
- Portas TCP `6112` e `9875` livres

Não precisas de instalar Python, MySQL ou Redis no host se usares Docker.

## Arranque rápido

### Windows / PowerShell

```powershell
git clone -b python3-modernization https://github.com/zzvictoor/Timeline.git
cd Timeline
Copy-Item .env.example .env
docker compose up --build
```

### Linux / macOS

```bash
git clone -b python3-modernization https://github.com/zzvictoor/Timeline.git
cd Timeline
cp .env.example .env
docker compose up --build
```

O Compose cria e liga automaticamente:

- `mariadb` — base de dados `timeline`
- `redis` — estado/cache online
- `timeline` — login server + world server

Por defeito:

- Login server: `0.0.0.0:6112`
- World server: `0.0.0.0:9875`
- World: `Gravity` (`id=100`)

Para acompanhar apenas o servidor:

```bash
docker compose logs -f timeline
```

Para parar:

```bash
docker compose down
```

Para apagar também a base de dados e começar de novo:

```bash
docker compose down -v
```

## Conta de teste

O `timeline.sql` original inclui a conta de desenvolvimento:

- username: `test`
- password: `password`
- nickname: `Peanut`

## Configuração

Copia `.env.example` para `.env` e altera o que precisares. As opções principais são:

```dotenv
TIMELINE_LOGIN_PORT=6112
TIMELINE_WORLD_PORT=9875
TIMELINE_WORLD_NAME=Gravity
TIMELINE_WORLD_ID=100
TIMELINE_WORLD_MAX=300

MYSQL_DATABASE=timeline
MYSQL_USER=timeline
MYSQL_PASSWORD=timeline
MYSQL_ROOT_PASSWORD=timeline-root
```

O nome da base de dados deve continuar a terminar em `line`, porque essa é uma convenção imposta pelo Timeline 7.x.

As integrações Firebase e Perspective são opcionais e ficam desligadas quando as respetivas variáveis estão vazias.

## Client / media server

O Timeline é o **emulador do servidor**, não é o client do Club Penguin nem contém todos os ficheiros de media necessários para jogar.

Para entrar no CPPS precisas de um client AS2/AS3 e dos assets/media que tenhas autorização para utilizar. O client deve ser configurado para apontar para o IP/domínio do teu servidor:

- login: `<IP_DO_SERVIDOR>:6112`
- world: `<IP_DO_SERVIDOR>:9875`

Para testar na mesma máquina usa `127.0.0.1`. Para outra máquina na LAN usa o IP local do PC que está a correr Docker. Para acesso pela Internet, abre/encaminha as portas TCP necessárias no router/firewall e usa um domínio/IP público adequado.

Browsers modernos não executam o Flash Player original, por isso a forma de arrancar o client depende do client/media stack que escolheres. Isto é separado do backend Timeline.

## Desenvolvimento sem Docker para a app

Também podes deixar apenas MariaDB + Redis no Docker e correr o servidor no host com Python 3.11:

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d mariadb redis
python Start.py
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d mariadb redis
python Start.py
```

Neste modo confirma que `MYSQL_HOST=127.0.0.1` e `REDIS_HOST=127.0.0.1` no `.env`.

## Verificação do port Python 3

```bash
python scripts/check_python3_sources.py
```

O checker compila diretamente o core já modernizado e aplica a mesma conversão temporária aos módulos legacy antes de os compilar.

## Próximos passos do port

1. Remover gradualmente a compatibilidade `lib2to3` convertendo handlers/plugins diretamente.
2. Fazer testes reais de handshake/login AS2 e AS3.
3. Cobrir Redis/DB/login com testes automatizados.
4. Quando a camada legacy desaparecer, subir o runtime para Python 3.12+.
