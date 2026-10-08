# UM982 GNSS datu apstrādes rīki

Python skriptu komplekts Unicore UM982 GNSS ierakstu savākšanai, arhivēšanai,
pārveidošanai un analīzei. Projekts apstrādā uztvērēja bināros ierakstus, veido
CSV un RINEX failus, aprēķina RTKLIB PPK risinājumus, atjauno kopējo viewer
datu kopu un ļauj kombinēt GNSS datus ar IMU mērījumiem.

## Iespējas

- UM982 datu ierakstīšana no seriālā/USB porta;
- ierakstu automātiska arhivēšana pēc GNSS laika;
- Unicore N4 ziņojumu eksportēšana uz CSV;
- UM982 BIN pārveidošana uz RINEX 3.03 vai 3.05;
- rover-only single, fixed PPK, float PPK un DGPS aprēķini ar RTKLIB;
- bāzes stacijas automātiska izvēle pēc RINEX laika pārklājuma;
- GNSS, PPK un IMU trajektoriju vizualizācija kartē;
- GNSS un IMU trajektorijas sapludināšana ar Kalmana filtru;
- lokāla pārlūka saskarne datu apstrādei un rezultātu salīdzināšanai.

## Ātrais starts

Priekšnosacījumi:

- Python 3.11 vai jaunāks;
- Git;
- RTKLIB 2.4.3 b34 `rnx2rtkp`, ja vajadzīgi single vai PPK aprēķini;
- interneta savienojums tiešsaistes karšu slāņu ielādei.

PowerShell:

```powershell
git clone <repozitorija-adrese>
cd src/gnss

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Copy-Item .env.example .env
```

`requirements.txt` ietver `pyserial`, kas vajadzīgs datu ierakstīšanai no
uztvērēja.

Minimālā darba plūsma jau saglabātam `.BIN` failam:

```powershell
# 1. Ievieto failu mapē in/, pēc tam arhivē.
python scripts/archive_in_recordings.py

# 2. Aizstāj <ieraksts> ar izveidotās out/ mapes nosaukumu.
python scripts/process_recording_all.py <ieraksts>

# 3. Atver apstrādes un rezultātu saskarni.
python scripts/viewer_server.py --port 8765
```

Pārlūkā atver `http://localhost:8765/app.html`.

### Braucienu datu analīze

Atver `http://localhost:8765/analysis.html` vai saiti **Datu analīze** skatītājā.
Pēc servera koda atjaunināšanas pārstartē `scripts/viewer_server.py`.
Lapa izmanto `out/` ierakstus, ļauj izvēlēties mēnesi un ierakstu un aprēķināt
mēneša salīdzinājumu. Tajā redzams punktu skaits un biežums, pozīcijas pieejamība,
laika iztrūkumi, satelīti, 3D nenoteiktība, uztvērēja vidējais 3D ātrums, virziena
kvalitāte un pēcapstrādes datu pieejamība. C/N₀ tiek nolasīts no RINEX 3 `S`
novērojumiem, ja tie ir pieejami; satelītu skaits netiek izmantots kā signāla
stipruma aizvietotājs. Pēcapstrādes punkti netiek pieskaitīti uztvērēja punktiem.
Aprēķini ir tikai lasīšanai, un to kešatmiņa atjaunojas, mainoties avota failiem.

## Projekta datu plūsma

```text
UM982 / IMU
    |
    +--> in/*.BIN ----------------------+
    |                                   |
    +--> in_imu/*                       v
                              archive_in_recordings.py
                                        |
                                        v
                              out/<ieraksts>/original/
                                        |
             +--------------------------+--------------------------+
             |                          |                          |
             v                          v                          v
          CSV dati                 RINEX OBS/NAV             viewer dati
             |                          |
             |                          +--> rover-only single
             |                          |
             |              base/rinex/ + rover RINEX
             |                          |
             |                          v
             |                    RTKLIB PPK/DGPS
             |                          |
             +------------+-------------+
                          v
                 viewer/ un GNSS+IMU
```

Galvenā vienība projektā ir viena ieraksta mape `out/<ieraksts>/`. Gandrīz
visiem skriptiem var padot tikai šīs mapes nosaukumu:

```powershell
python scripts/process_recording_all.py 20260503_132939Z_test_log_1
```

Var padot arī pilnu vai relatīvu ceļu:

```powershell
python scripts/process_recording_all.py out/20260503_132939Z_test_log_1
```

## Mapju struktūra

```text
.
|-- base/
|   |-- raw/                 # bāzes stacijas neapstrādātie dati
|   |-- rinex/<bāze>/        # PPK izmantotie bāzes RINEX faili
|   `-- notes/<bāze>/        # antenas, stacijas un importa piezīmes
|-- config/
|   |-- ppk.yaml             # RTKLIB izpildfaila un rezultātu konfigurācija
|   |-- rtklib_ppk_fixed.conf
|   |-- rtklib_ppk_float.conf
|   `-- rtklib_ppk_dgps.conf
|-- in/                      # jauni rover BIN ieraksti
|-- in_base/                 # ienākošas publisko bāzes staciju pakotnes
|-- in_imu/                  # jauni IMU BIN vai CSV ieraksti
|-- out/<ieraksts>/          # viena rover sesija un visi tās rezultāti
|-- scripts/                 # komandrindas rīki
|-- viewer/                  # ģenerētais skatītājs un vadības panelis
|-- .env.example
`-- requirements.txt
```

Vienas apstrādātas sesijas struktūra:

```text
out/<ieraksts>/
|-- original/
|   `-- LOG00001.BIN
|-- csv/
|   |-- bestnavxyz.csv
|   |-- bestnavxyz_filtered.csv
|   |-- location_heading_xyz.csv
|   |-- message_summary.csv
|   `-- records_index.csv
|-- rinex/
|   |-- LOG00001.26O
|   |-- LOG00001.26P
|   `-- LOG00001_conversion_report.txt
|-- ppk/
|   |-- observation_single.csv
|   |-- solution.csv
|   |-- solution_float.csv
|   |-- solution_dgps.csv
|   `-- ppk_report*.txt
|-- imu/
|   |-- raw/
|   |-- assignment.csv
|   `-- kalman_*.csv
`-- other/
    `-- process_all_report.txt
```

`in/`, `in_base/`, `in_imu/`, `out/`, bāzes staciju dati un ģenerētie
`viewer/data/` faili ir lokāli darba dati un netiek glabāti Git repozitorijā.

## Ieraksta iegūšana un arhivēšana

Tieša UM982 datu ierakstīšana:

```powershell
python scripts/capture/capture_um982_usb.py COM7 LOG00001.BIN
```

Ja faila nosaukums nav norādīts, skripts izveido
`in/capture_YYYYMMDD_HHMMSS.BIN`. Ierakstīšanu aptur ar `Ctrl+C`.

Jau esošu failu var vienkārši ievietot `in/`. Pēc tam:

```powershell
python scripts/archive_in_recordings.py
```

Arhivētājs:

- nolasa pirmo derīgo GPS laiku no N4/OEM paketes;
- izveido `out/YYYYMMDD_HHMMSSZ_<faila-nosaukums>/`;
- pārvieto oriģinālu uz `original/`;
- izveido rezultātu apakšmapes;
- ar SHA-256 pārbauda, vai identisks fails jau nav arhivēts;
- ja GNSS laiku nevar atrast, mapes nosaukumā izmanto lokālo laiku.

Pēc noklusējuma tiek arhivēti tikai `.BIN` faili. Citiem failiem:

```powershell
python scripts/archive_in_recordings.py --all-files
```

## Pilnā apstrāde

Ieteicamā galvenā komanda:

```powershell
python scripts/process_recording_all.py <ieraksts>
```

Tā secīgi:

1. eksportē Unicore N4 ziņojumus uz CSV;
2. izfiltrē rindas ar nulles koordinātām;
3. izveido RINEX OBS un NAV failus;
4. mēģina aprēķināt rover-only single risinājumu;
5. aprēķina PPK, ja padots `--base`;
6. atjauno kopējo `viewer/` datu kopu;
7. ieraksta visu soļu izvadi `other/process_all_report.txt`.

Vairāki vai visi ieraksti:

```powershell
python scripts/process_recording_all.py <ieraksts-1> <ieraksts-2>
python scripts/process_recording_all.py all
```

Pilnā apstrāde ar automātiski piemeklētu bāzes staciju:

```powershell
python scripts/process_recording_all.py all --base auto
python scripts/process_recording_all.py all --base auto:JURM
```

Noderīgas opcijas:

```text
--base <nosaukums|auto>       ieslēdz PPK aprēķinu
--ppk-mode <režīms>           all, fixed, float, dgps, both vai configured
--rinex-obs-source <avots>    izvēlas UM982 novērojumu ziņojumu
--skip-observation-single     izlaiž rover-only single aprēķinu
--skip-viewer-update          neatjauno viewer/
--rnx2rtkp <ceļš>             īslaicīgi pārraksta RTKLIB izpildfaila ceļu
```

Pilnu opciju sarakstu var apskatīt ar:

```powershell
python scripts/process_recording_all.py --help
```

## CSV un RINEX atsevišķi

Unicore N4 ziņojumu eksports:

```powershell
python scripts/converting/to_csv/unicore_n4_extract.py <ieraksts>
python scripts/converting/to_csv/filter_zero_coords.py <ieraksts>
```

Vispārīgais BIN, RTKLIB POS vai RINEX uz CSV pārveidotājs:

```powershell
python scripts/converting/to_csv/gnss_to_csv.py <ieraksts>
```

Pilnais RINEX 3.05 pārveidotājs:

```powershell
python scripts/converting/to_rinex/rinex305_toolkit/rinex305_toolkit/rinex305_conversion_full.py <ieraksts>
```

Automātiskā novērojumu avotu prioritāte ir:

```text
rangecmpb -> obsvmcmpb -> obsvmb -> rangeb
```

Master vai slave antenas avotu var norādīt manuāli:

```powershell
python scripts/converting/to_rinex/rinex305_toolkit/rinex305_toolkit/rinex305_conversion_full.py <ieraksts> --obs-source obsvmcmpb
python scripts/converting/to_rinex/rinex305_toolkit/rinex305_toolkit/rinex305_conversion_full.py <ieraksts> --obs-source obsvhcmpb --basename rover_slave
```

Atbalstītie avoti: `auto`, `rangeb`, `rangecmpb`, `obsvmb`, `obsvmcmpb`,
`obsvhb` un `obsvhcmpb`.

Rezultātā var tikt izveidoti:

```text
<nosaukums>.yyO    novērojumi
<nosaukums>.yyP    jaukta GNSS navigācija
<nosaukums>.yyN    GPS navigācija
<nosaukums>.yyG    GLONASS navigācija
<nosaukums>.yyC    BeiDou navigācija
<nosaukums>.yyL    Galileo navigācija
```

GPS nedēļa parasti tiek noteikta automātiski. `--date` vai `--gps-week` ir
vajadzīgs tikai tad, ja automātiskā noteikšana neizdodas.

## RTKLIB un PPK

Nokopē `.env.example` uz `.env` un norādi lokālo RTKLIB ceļu:

```dotenv
RTKLIB_VERSION="2.4.3 b34"
RTKLIB_RNX2RTKP_EXE="C:/tools/RTKLIB_2.4.3_b34/bin/rnx2rtkp.exe"
RTKLIB_CONFIG_FILE="config/rtklib_ppk_fixed.conf"
```

Linux vai macOS gadījumā pēc RTKLIB kompilēšanas ceļš parasti norāda uz:

```text
<RTKLIB>/app/consapp/rnx2rtkp/gcc/rnx2rtkp
```

`.env` satur konkrētās darbstacijas iestatījumus un nav jākomitē Git.

### Bāzes stacijas dati

Manuāli sakārtoti bāzes RINEX faili jāievieto:

```text
base/rinex/<bāzes-nosaukums>/
```

Publiskas stacijas pakotni no `in_base/` var importēt:

```powershell
python scripts/ppk/import_base_rinex.py <pakotnes-mape>
```

Imports atdala RINEX failus uz `base/rinex/<bāze>/`, piezīmes uz
`base/notes/<bāze>/` un izveido `import_report.txt`.

### PPK palaišana

```powershell
python scripts/ppk/run_ppk.py <ieraksts> --base <bāzes-nosaukums>
```

`--base` pieņem:

- mapes nosaukumu zem `base/rinex/`;
- pilnu ceļu uz bāzes RINEX mapi;
- `auto`, lai izvēlētos staciju pēc OBS laika pārklājuma;
- `auto:JURM` vai PowerShell pēdiņās `"auto|JURM"`, lai papildus filtrētu pēc
  stacijas nosaukuma.

Pēc noklusējuma `--mode all` aprēķina:

| Režīms | RTKLIB konfigurācija | Galvenie faili |
|---|---|---|
| fixed | `rtklib_ppk_fixed.conf` | `solution.pos`, `solution.csv` |
| float | `rtklib_ppk_float.conf` | `solution_float.pos`, `solution_float.csv` |
| dgps | `rtklib_ppk_dgps.conf` | `solution_dgps.pos`, `solution_dgps.csv` |

Tikai viens režīms:

```powershell
python scripts/ppk/run_ppk.py <ieraksts> --base auto --mode fixed
python scripts/ppk/run_ppk.py <ieraksts> --base auto --mode float
python scripts/ppk/run_ppk.py <ieraksts> --base auto --mode dgps
```

Rover-only risinājums bez bāzes:

```powershell
python scripts/ppk/run_observation_single.py <ieraksts>
```

Uztvērēja parastā risinājuma un fixed PPK salīdzinājums:

```powershell
python scripts/ppk/compare_ppk_to_regular.py <ieraksts>
```

Tas izveido `ppk/regular_vs_ppk.csv` un
`ppk/regular_vs_ppk_report.txt`.

## Skatītājs

Kopējā visu ierakstu viewer datu atjaunošana:

```powershell
python scripts/maps/build_recording_viewer.py
```

Pilnā lokālā saskarne:

```powershell
python scripts/viewer_server.py --host localhost --port 8765
```

Atver `http://localhost:8765/app.html`. Saskarne ļauj:

- izvēlēties ierakstu un ieslēgt/izslēgt trajektoriju slāņus;
- palaist CSV, RINEX, single, PPK vai pilnās apstrādes soli;
- pievienot IMU ierakstu;
- mainīt laika nobīdi un Kalmana filtra parametrus;
- salīdzināt vairākus GNSS, PPK un IMU rezultātus.

Serveris paredzēts lokālai lietošanai. Nepublicē to internetā bez papildu
autentifikācijas un drošības ierobežojumiem.

## IMU un Kalmana filtrs

### Manuāla laika sasaiste

Atver `http://localhost:8765/alignment.html` (navigācijā **Laika sasaiste**).
Pēc servera koda atjaunināšanas pārstartē `scripts/viewer_server.py`.
Izvēlies GNSS sesiju, pieejamu avotu un IMU failu, tad ielādē grafikus.
Abiem grafikiem ir kopīga laika ass: peles ritenis tuvina, vilkšana pārvieto logu.
IMU grafikā var izvēlēties asi; GNSS grafikā — horizontālo pārvietojumu no
sākuma, no koordinātām iegūtu ātrumu vai tā atvasinājumu.

Atzīmē vienu un to pašu notikumu katrā grafikā un nospied **Savietot atzīmes**.
Pozitīva nobīde novieto IMU sākumu vēlāk par pirmo GNSS punktu.
Nobīdi var precizēt skaitliski. **Saglabāt sasaisti** ieraksta
`out/<sesija>/imu/alignment_<avots>_<imu>.json`; šī pati failu/avota izvēle
atjauno saglabāto nobīdi. Lapa izveido CLI komandu ar `--imu-start-utc`, ko
izmantot turpmākajam Kalmana aprēķinam. Esošās apstrādes lapas iestatījumi
netiek automātiski pārrakstīti.

Grafiks saglabā signāla minimumu un maksimumu katrā ekrāna pikseļa intervālā.
Tuvinot izmanto pilnos mērījumus. Nekustīgam ierakstam ar kustības salīdzināšanu
nepietiek, lai noteiktu laika nobīdi. Ievades solis nav precizitātes garantija.

Ievieto IMU `.BIN` vai `.csv` failus `in_imu/`.

Atrodi ticamākās IMU un GNSS sesiju atbilstības pēc ilguma:

```powershell
python scripts/assign_imu_recording.py list --source bestnav
```

Piešķir IMU failu konkrētam GNSS ierakstam:

```powershell
python scripts/assign_imu_recording.py assign <ieraksts> brauciens_1.BIN
```

BIN fails tiek nokopēts uz `imu/raw/`, pārveidots uz CSV un reģistrēts
`imu/assignment.csv`.

GNSS un IMU Kalmana trajektorija:

```powershell
python scripts/imu_kalman.py <ieraksts> `
  --imu out/<ieraksts>/imu/brauciens_1.csv `
  --source fixed_ppk `
  --auto-align `
  --update-viewer
```

### Sapludināšanas algoritms (`scripts/gnss_imu_fusion.py`)

`imu_kalman.py` izmanto Kalmana filtru ar RTS izlīdzināšanu. IMU šeit ir tikai
3 asu akselerometrs (bez žiroskopa), tāpēc orientāciju no tā iegūt nevar:

- stāvoklis `[E, N, vE, vN, b]` (b ir akselerometra nobīde gar kustības virzienu);
- IMU dod paredzēšanu ar garenisko paātrinājumu. Kustības ass sensora koordinātās
  tiek noteikta automātiski (mazāko kvadrātu fits pret GNSS paātrinājumu), un
  gravitācijas daļa `g·sin(slīpums)` tiek atņemta, izmantojot GNSS augstuma profilu;
- GNSS pozīcija (un bestnav Doppler ātrums, ja ir) koriģē filtru reālajos GNSS
  mērījumu laikos, nevis interpolētos punktos;
- kļūdaini GNSS punkti tiek noraidīti ar innovācijas vārtiem (`outlier_gate_sigma`)
  un daļēji nosvērti ar Huber svaru (`huber_sigma`). Ja punkti tiek noraidīti ilgāk par
  `max_reject_duration_s`, filtrs tos pieņem atkal ar palielinātu nenoteiktību;
- ZUPT: kad GNSS ātrums un IMU trokšņi norāda uz stāvēšanu, ātrums tiek turēts uz 0;
- ja IMU neatbilst GNSS paātrinājumam (`forward_axis_r2 < min_axis_r2`, parasti
  nepareiza laika sasaiste), IMU tiek ignorēts un rezultāts ir tikai no GNSS.

**Noklusētie parametri** ir `config/fusion_defaults.json`. GNSS pozīcijas σ pēc noklusējuma
tiek ņemta no avota (`fixed_ppk` 0.05 m, `float_ppk` 0.3, `dgps` 0.8, `bestnav` pēc
`position_type`, `observation` 2.5). Izmaiņas var norādīt:

```powershell
# vienam palaidienam
python scripts/imu_kalman.py <ieraksts> --imu <imu> --source fixed_ppk `
  --position-sigma-m 0.1 --outlier-gate-sigma 4 --fusion-set smooth=false

# cits konfigurācijas fails
python scripts/imu_kalman.py <ieraksts> --imu <imu> --fusion-config my_fusion.json
```

Viewer cilnē Kalman tukši lauki **GNSS sigma / Accel noise / Update s** nozīmē
automātisko vērtību; **Fusion options** pieņem `key=value; key=value`.

**GNSS pārtraukuma tests.** `--gnss-outage 60:75` (sekundes no pārklāšanās sākuma)
noņem GNSS šajā logā un atskaitē parāda kļūdu pret noņemtajiem punktiem. Tā var
objektīvi novērtēt, vai IMU palīdz. Piemēram, pārtraukums taisnā posmā pie ~28 m/s
deva ~0.3 m kļūdu, bet pagriezienos (bez žiroskopa sānu kustība nav novērojama) kļūda
ir ievērojami lielāka.

Papildu izejas: `kalman_*.csv` tagad satur `sigma_e_m`, `sigma_n_m`, `bias_mps2`,
`gnss_status` (`used/downweighted/rejected/reacquired/outage/none`) un
`innovation_sigma`; `fusion_gnss_kalman_*.csv` saraksta katru GNSS epohu ar statusu.
Atskaites fails satur visus izmantotos parametrus.

**Svarīgi:** sapludināšanas kvalitāte ir ļoti atkarīga no pareizas IMU/GNSS laika
sasaistes. `--auto-align` ir ticams tikai ar korelāciju virs ~0.3; pārbaudi
`forward_axis_r2` (labs ≥ 0.5) atskaitē.

### Sapludināšanas lapa un vairāki aprēķini

`http://localhost:8765/alignment.html` (navigācijā **Sapludināšana**) ir grafiska saskarne sešos soļos:
dati, laika sasaiste (automātiska meklēšana + savietošana ar roku), iestatījumi ar paskaidrojumiem,
aprēķins, rezultāts un aprēķinu salīdzināšana. Pēc servera koda atjaunināšanas pārstartē `scripts/viewer_server.py`.

Vienam GNSS ierakstam (tam pašam avotam un IMU) var izveidot cik vien vēlies aprēķinu ar dažādiem
iestatījumiem. Katrs aprēķins tiek saglabāts atsevišķi:

- faili `out/<ieraksts>/imu/kalman_<avots>_<imu>_<laiks>.csv` (un `…_report.txt`, `fusion_gnss_….csv`);
- iestatījumi, rezultātu metrikas, nosaukums un piezīme datubāzē `out/fusion_runs.sqlite`
  (SQLite; to var atvērt ar jebkuru SQLite rīku, tabula `fusion_runs`).

6. solī vari atzīmēt vairākus aprēķinus un redzēt to trajektorijas vienā attēlā, salīdzināt metrikas,
pārdēvēt tos, pievienot piezīmes, **ielādēt aprēķina iestatījumus atpakaļ 3. solī** un dzēst aprēķinu
(tiek dzēsti arī tā faili). Vecāki `kalman_*.csv` faili bez datubāzes ieraksta tiek rādīti tikai
apskatei.

Akselerometra bias kalibracija no statiska IMU ieraksta:

```powershell
python scripts/imu_bias_calibration.py in_imu/static.BIN `
  --profile static_table `
  --start-s 2 `
  --end-s 60
```

Pilna IMU pēcapstrādes profila kalibrācija (bias + drift/ZUPT iestatījumi) no nekustīga brauciena:

```powershell
python scripts/imu_processing_profile.py in_imu/brauciens_5.BIN `
  --profile from_static_brauciens_5 `
  --recording out/20260521_125445Z_LOG00005 `
  --start-s 2 `
  --end-s 60
```

Profils tiek saglabats `config/imu_processing_profiles.csv`. Pec tam to var pielietot
Kalman vai IMU diagnostikas aprēķinam (viewer: izvēlies profilu un Calculate Kalman):

```powershell
python scripts/imu_kalman.py <ieraksts> `
  --imu out/<ieraksts>/imu/brauciens_1.csv `
  --source bestnav `
  --accel-bias -0.0457,0.0338,0.5442 `
  --drift-correct `
  --static-speed-mps 0.2 `
  --accel-residual-gate-mps2 0.065 `
  --update-viewer
```

Vai viewer dashboard IMU cilnē: **Calibrate from static recording** → izvēlies to pašu **IMU processing profile** uz kustīgā brauciena → **Calculate Kalman with profile**.

Vecais bias-only fails joprojām lasās kā migrācija uz processing profiliem.

GNSS avoti:

- `bestnav` - uztvērēja koordinātas;
- `fixed_ppk` - `ppk/solution.csv`;
- `float_ppk` - `ppk/solution_float.csv`;
- `dgps` - `ppk/solution_dgps.csv`;
- `observation` - `ppk/observation_single.csv`.

Laika sasaistes varianti:

```text
--time-offset-s N       IMU sākums = GNSS sākums + N sekundes
--imu-start-utc <laiks> absolūts IMU sākuma UTC laiks
--auto-align            nobīdes meklēšana pēc kustības korelācijas
```

Galvenie rezultāti:

```text
imu/kalman_<avots>_<imu>.csv
imu/imu_dead_reckoning_<avots>_<imu>.csv
imu/imu_drift_corrected_<avots>_<imu>.csv
```

Drift korekcija pirms Kalman (pēc noklusējuma ieslēgta): residual gate + ZUPT, kad GNSS ātrums ≈ 0.
Parametri: `--static-speed-mps`, `--accel-residual-gate-mps2`, `--no-drift-correct`.

Zemas `--auto-align` pārliecības gadījumā rezultāts jāpārbauda pret zināmu
`--time-offset-s` vai `--imu-start-utc`.

## Papildu rīki

| Skripts | Uzdevums |
|---|---|
| `scripts/archive_in_recordings.py` | arhivē jaunus rover ierakstus |
| `scripts/session_paths.py` | kopīgās sesiju ceļu funkcijas |
| `scripts/gnss_track_utils.py` | kopīgās GNSS/PPK trajektoriju un RTKLIB helper funkcijas |
| `scripts/capture/capture_um982_usb.py` | ieraksta UM982 seriālos datus |
| `scripts/converting/to_csv/unicore_n4_extract.py` | eksportē N4 ziņojumus uz CSV |
| `scripts/converting/to_csv/filter_zero_coords.py` | izmet nulles koordinātu rindas |
| `scripts/converting/to_csv/gnss_to_csv.py` | vispārīgs GNSS/POS uz CSV rīks |
| `scripts/converting/filter_recording_messages.py` | izveido BIN kopiju bez norādītiem ziņojumu ID |
| `scripts/ppk/import_base_rinex.py` | importē bāzes stacijas pakotni |
| `scripts/ppk/run_ppk.py` | palaiž RTKLIB PPK/DGPS |
| `scripts/ppk/run_observation_single.py` | aprēķina rover-only single risinājumu |
| `scripts/ppk/compare_ppk_to_regular.py` | salīdzina uztvērēja un PPK koordinātas |
| `scripts/maps/build_recording_viewer.py` | atjauno visu sesiju skatītāju |
| `scripts/assign_imu_recording.py` | piesaista IMU failu GNSS sesijai |
| `scripts/imu_kalman.py` | veido GNSS+IMU trajektoriju |
| `scripts/ImuBinToCSV.py` | atsevišķi dekodē IMU BIN uz CSV tekstu |
| `scripts/viewer_server.py` | palaiž lokālo saskarni un API |
| `scripts/process_recording_all.py` | izpilda galveno pilno darba plūsmu |

Piemērs BIN ziņojumu filtrēšanai:

```powershell
python scripts/converting/filter_recording_messages.py <ieraksts> `
  --output-name <jauns-ieraksts> `
  --remove-ids 138,139
```

## Konfigurācija

Aktuālajai darba plūsmai svarīgi faili:

- `.env` - lokālais RTKLIB izpildfaila ceļš;
- `config/ppk.yaml` - PPK rezultātu failu nosaukumi un `.env` mainīgo saites;
- `config/rtklib_ppk_fixed.conf` - kinemātisks risinājums ar ambiguity resolution;
- `config/rtklib_ppk_float.conf` - kinemātisks float risinājums;
- `config/rtklib_ppk_dgps.conf` - koda diferenciālais rezerves risinājums.

`config/project.yaml` un `scripts/pipeline/process_trip.py` pieder vecākai
cauruļvada versijai. `process_trip.py` tikai izvada novecošanas ziņojumu un
norāda uz `scripts/process_recording_all.py`.

## Problēmu novēršana

**`No .BIN file found`**

Pārbaudi, vai sesijā ir tieši viens fails zem
`out/<ieraksts>/original/`.

**`Could not find a receiver CSV`**

Vispirms palaid `unicore_n4_extract.py` un `filter_zero_coords.py` vai pilno
`process_recording_all.py`.

**`No module named serial`**

```powershell
python -m pip install -r requirements.txt
```

**RTKLIB izpildfails nav atrasts**

Pārbaudi `RTKLIB_RNX2RTKP_EXE` vērtību `.env` vai izmanto
`--rnx2rtkp <pilns-ceļš>`.

**Automātiski netiek atrasta bāzes stacija**

Pārbaudi, vai rover un bāzes OBS failu `TIME OF FIRST OBS` un
`TIME OF LAST OBS` intervāli pārklājas. Vajadzības gadījumā norādi bāzes mapi
manuāli.

**PPK rezultāts izskatās nekorekts**

Izlasi `ppk/ppk_report*.txt` un `rnx2rtkp_stderr*.txt`. Pārbaudi bāzes stacijas
koordinātas, antenas informāciju, RINEX laika pārklājumu, izmantoto novērojumu
avotu un RTKLIB konfigurāciju. `solution.csv` esamība pati par sevi negarantē
derīgu fixed risinājumu.

## Piezīmes izstrādei

- Skripti ir paredzēti palaišanai no projekta saknes.
- Katrai sesijai `original/` mapē jābūt tieši vienam rover `.BIN` failam.
- Ģenerētie un lielie mērījumu faili netiek komitēti Git.
- Pirms būtiskām izmaiņām pārbaudi komandas ar `--help`.
- Projektā pašreiz nav automatizētu testu komplekta.
- Repozitorijā nav norādīta atsevišķa licence.
