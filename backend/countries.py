"""Where a news source comes from: the country of the outlet (not of the
story), shown as a flag on the TV.

From the catalog's region when it names a country, else the site's
country-code domain (.de, .co.uk, .jp…), else the table below for sites on
generic domains (.com, .org…). Unknown: no flag — never a guessed one.
"EU" and "UN" are the European Union's and the United Nations' own flags,
for their agencies."""
import re

# Country-code domains used as vanity names, not as a country.
VANITY = {"io", "ai", "co", "me", "tv", "fm", "ly", "gg", "sh", "so", "to", "ws", "cc", "rs", "la", "is", "st", "pub", "news"}
TLD = {"uk": "GB", "eu": "EU"}

# By title (shared platforms: YouTube, Medium, Substack…).
TITLES = {
    "3Blue1Brown": "US", "AI Explained": "GB", "Andrej Karpathy": "US", "Lex Fridman": "US",
    "Two Minute Papers": "HU", "Yannic Kilcher": "CH", "Hak5": "US", "John Hammond": "US",
    "LiveOverflow": "DE", "NetworkChuck": "US", "Netflix Tech Blog": "US", "Import AI Newsletter": "US",
    "Google Project Zero": "US", "Lil'Log": "US", "Avian Flu Diary": "US",
    "Amazon Science Blog": "US", "Google AI Blog": "US", "Google DeepMind": "GB", "Microsoft AI Blog": "US",
    "NVIDIA AI Blog": "US", "Notion Engineering": "US", "Schneier on Security": "US", "GitLab Blog": "US",
    "Alpha Architect": "US", "Google Quantum AI": "US", "KrASIA (Asia tech)": "SG",
    "Techpoint Africa": "NG", "GamesIndustry.biz": "GB", "World Rugby": "IE", "AeroTime": "LT",
    "Offshore Energy": "NL", "Abnormal Returns": "US", "C&EN": "US",
}

_US = """agfundernews al-monitor anandtech androidauthority anthropic apnews arstechnica arxiv ascopubs acpjournals
astronomy atlasobscura automationworld avclub aviationweek avweb aws.amazon azure.microsoft bair.berkeley
bigthink billboard biopharmadive biorxiv biospace bitcoinmagazine bleepingcomputer blockworks blogs.microsoft
blogs.nvidia bloomberg bostondynamics breakingdefense broadinstitute businessinsider calculatedriskblog
canarymedia caranddriver cardiovascularbusiness cbinsights cbssports cell centauri-dreams cfr chalkbeat
chinatalk cisa civileats cjr cleantechnica climate.gov clinicaltrials cloudflare cloud.google cnbc cnet
cntraveler coindesk collider-us commsupdate consequence contagionlive core77 crowdstrike crunchbase
cset.georgetown csis csmonitor css-tricks cyberscoop darkreading databricks deadline decrypt defensenews
defenseone digiday distill docker dropbox eater edition.cnn edsurge edweek e360.yale eff ehn electrek
elastic engadget engineering.linkedin eng.uber espn espncricinfo ethereum eugeneyan fastcompany
federalreserve fiercebiotech fiercehealthcare fiercepharma flowingdata fooddive fool forbes foreignaffairs
foreignpolicy fortune gamedeveloper genengnews github gizmodo googleprojectzero grafana grist hacks.mozilla
harvard hashicorp healthcaredive heatmap highscalability hollywoodreporter hrdive hrw huggingface icinsights
ign importai inc indiewire insideclimatenews insideevs insidehighered interconnects isc.sans jalopnik
jamanetwork joelonsoftware journals.plos kffhealthnews knowablemagazine kotaku krebsonsecurity kubernetes
lawfareblog lightreading lilianweng linuxfoundation lithub livescience lwn macrumors madinamerica
magazine.sebastianraschka malwarebytes mandiant marginalrevolution marketwatch mathvoices.ams medcitynews
medpagetoday medrxiv medtechdive militarytimes mit mongabay motor1 motorsport nasa nasaspaceflight nejm
neurosciencenews newyorker niemanlab nimh.nih nngroup noahpinion nomadicmatt npr nvd.nist nytimes
onclive onemileatatime openai ai.meta opensource oreilly ourworldindata-us pharmavoice phoronix physics.aps
pitchfork planetary pnas polygon poynter protocol psychiatrictimes psypost publishersweekly python
quantamagazine quantocracy quantumcomputingreport radiologybusiness rand rcrwireless realclimate
recordedfuture redhat research.ibm responsiblestatecraft restofworld retaildive ritholtz rollingstone
sciencedaily sciencenews science scientificamerican securityweek seekingalpha semafor semianalysis
semiengineering semiwiki servethehome simonwillison skift slashfilm smallwarsjournal smithsonianmag
space spacenews spacex spectrum.ieee sports.yahoo sreweekly stackoverflow statnews stereogum stratechery
stripe supplychaindive talosintelligence targetedonc techcrunch technologyreview technews.acm techonomy
theatlantic theblock thedefiant thedrive thegradient theinformation themarginalian thenewstack
thepointsguy thequantuminsider therobotreport thetransmitter theverge thewirechina thisiscolossal
threatpost tomshardware twz utilitydive variety venturebeat wallstreet wandb warontherocks wired wsj
wwwnc.cdc ycombinator zdnet 5gamericas cdc fda nih alzforum cidrap umn assemblyai crowdstrike lobste
paulgraham martinfowler-us 9to5google 9to5mac daringfireball pcgamer eetimes towardsdatascience nautil
teslarati espnfc salon axios politico thehill pbs abcnews cbsnews latimes usatoday nationalgeographic
reason abajournal abovethelaw scotusblog law jurist natesilver""".split()

HOSTS = {h: "US" for h in _US}
HOSTS.update({
    # Europe
    "aeon": "GB", "acolyer": "GB", "aibusiness": "GB", "amnesty": "GB", "autosport": "GB", "azom": "GB",
    "bbc": "GB", "bmj": "GB", "cancerresearchuk": "GB", "carbonbrief": "GB", "cepr": "GB",
    "chemistryworld": "GB", "clinicaltrialsarena": "GB", "crash": "GB", "creativebloq": "GB",
    "cyclingnews": "GB", "dezeen": "GB", "economist": "GB", "elifesciences": "GB", "energymonitor": "GB",
    "energy-storage": "GB", "eurogamer": "GB", "finextra": "GB", "fintechfutures": "GB", "flightglobal": "GB",
    "formula1": "GB", "fourfourtwo": "GB", "frontlinegenomics": "GB", "ft": "GB", "itsnicethat": "GB",
    "link.springer": "GB", "martinfowler": "GB", "medicaldevice-network": "GB", "medicalxpress": "GB",
    "middleeasteye": "GB", "musicbusinessworldwide": "GB", "nakedsecurity.sophos": "GB", "sophos": "GB",
    "nature": "GB", "newscientist": "GB", "news-medical": "GB", "nintendolife": "GB", "nme": "GB",
    "oilprice": "GB", "ourworldindata": "GB", "pharmaceutical-technology": "GB", "phys": "GB",
    "physicsworld": "GB", "plus.maths": "GB", "pushsquare": "GB", "purexbox": "GB", "quantstart": "GB",
    "racefans": "GB", "reuters": "GB", "rockpapershotgun": "GB", "screendaily": "GB", "sifted": "GB",
    "skysports": "GB", "techradar": "GB", "techxplore": "GB", "telecoms": "GB", "telecomtv": "GB",
    "the-race": "GB", "theartnewspaper": "GB", "theguardian": "GB", "thelancet": "GB", "theregister": "GB",
    "videogameschronicle": "GB", "wallpaper": "GB", "workplaceinsight": "GB", "world-nuclear-news": "GB",
    "climatechangenews": "GB", "pressgazette": "GB", "independent": "GB", "eenewseurope": "EU",
    "dw": "DE", "kde": "DE", "labiotech": "DE", "linux-magazine": "DE", "notebookcheck": "DE",
    "pv-magazine": "DE", "smashingmagazine": "DE", "france24": "FR", "euronews": "FR", "jeuneafrique": "FR",
    "theafricareport": "FR", "navalnews": "FR", "designboom": "IT", "theaviationist": "IT",
    "bellingcat": "NL", "globalvoices": "NL", "crisisgroup": "BE", "euractiv": "BE", "politico.eu": "BE",
    "tech.eu": "BE", "project-syndicate": "CZ", "balkaninsight": "RS", "notesfrompoland": "PL",
    "gsmarena": "BG", "medicalfuturist": "HU", "healthpolicy-watch": "CH", "home.cern": "CH",
    "ecb.europa": "EU", "ecdc.europa": "EU", "ema.europa": "EU", "enisa.europa": "EU",
    "climate.copernicus": "EU", "esa": "EU", "eso": "EU", "eurosurveillance": "EU", "eu-startups": "EU",
    # Asia, Middle East, Africa, Americas, Oceania
    "aitimes": "KR", "koreajoongangdaily.joins": "KR", "alibabacloud": "CN", "cloud.tencent": "CN",
    "ithome": "CN", "mydrivers": "CN", "pandaily": "CN", "research.baidu": "CN", "digitimes": "TW",
    "trendforce": "TW", "asia.nikkei": "JP", "scmp": "HK", "asianscientist": "SG", "e27": "SG",
    "techinasia": "SG", "entrackr": "IN", "itsfoss": "IN", "thehackernews": "IN", "yourstory": "IN",
    "aljazeera": "QA", "arabnews": "SA", "wamda": "AE", "techcabal": "NG", "disruptafrica": "ZA",
    "contxto": "MX", "archdaily": "CL", "androidpolice": "CA", "collider": "CA", "simpleflying": "CA",
    "infoq": "CA", "universetoday": "CA", "atlassian": "AU", "startupdaily": "AU",
    "un": "UN", "who": "UN", "news.un": "UN", "iranintl": "GB", "timesofisrael": "IL",
})


def _host(url: str) -> str:
    h = re.sub(r"^https?://", "", url or "", flags=re.I).split("/")[0].split(":")[0].lower()
    return re.sub(r"^(www\d?|feeds?|rss|news|api|connect|newsfeed|syndication|e00-[a-z]+|xml2|rssfeeds|assets|blog|blogs|m)\.", "", h)


def country(url: str, title: str = "", region: str | None = None) -> str | None:
    """ISO code of the outlet's country, or "EU"/"UN", or None."""
    if title in TITLES:
        return TITLES[title]
    if region and re.fullmatch(r"[A-Z]{2}", region):
        return region
    host = _host(url)
    if not host:
        return None
    parts = host.split(".")
    # Longest match first: "politico.eu", then "politico".
    for i in range(len(parts) - 1):
        key = ".".join(parts[i:-1])
        if key in HOSTS:
            return HOSTS[key]
    tld = parts[-1]
    if tld in TLD:
        return TLD[tld]
    if len(tld) == 2 and tld not in VANITY:
        return tld.upper()
    if tld in ("gov", "mil", "edu"):
        return "US"
    return None
