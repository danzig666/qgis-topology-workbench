# Topology Workbench

Önálló QGIS-bővítmény a topológiai hibák keresésére és feldolgozására, a QGIS felületi nyelvét követő angol és magyar felülettel. Telepíthető csomag: `topology_workbench-1.1.0.zip`, elérhető a [GitHub-kiadásoknál](https://github.com/danzig666/qgis-topology-workbench/releases). [English documentation](../README.md).

## Telepítés

1. QGIS → **Bővítmények → Bővítmények kezelése és telepítése → Telepítés ZIP-ből**.
2. Válaszd a `topology_workbench-1.1.0.zip` fájlt, majd telepítsd és engedélyezd a **Topology Workbench** bővítményt.
3. Nyisd meg az eszközt az eszköztári ikonról vagy a **Vektor → Topology Workbench** menüből.

A plugin QGIS **3.44+ és 4.x** verziókra készült. Valódi QGIS **3.44.9 / Qt5** és **4.2.2 / Qt6** környezetben ellenőrizve. Külső Python-csomagot nem kell telepíteni. A későbbi QGIS-verziók API-változásai további ellenőrzést igényelhetnek.

A bővítmény az aktív QGIS-felületi nyelvet használja: magyar QGIS esetén magyarul, angol QGIS esetén angolul jelenik meg. Más nyelveknél angolra vált. A szabálycímek, leírások, felületi elemek, saját hibaüzenetek és az export szöveges tartalma is ezt követi; a rétegnevek, elem- és szabályazonosítók, JSON-kulcsok és exportmezőnevek változatlanok. A nyelv a bővítmény indításakor kerül kiválasztásra; a QGIS nyelvváltása után indítsd újra a QGIS-t. A QGIS vagy GEOS által adott natív diagnosztikai szöveg az adott könyvtárból érkezik.

## Használat

- **Új szabály:** válassz ellenőrzést, majd a réteg nevének bármely részletére keresve válassz réteget a találati listából. A felület az adott szabályhoz megfelelő geometriatípusokra szűri a rétegeket. A referenciaréteg szintén kereshető.
- **Alapellenőrzések:** az aktív rétegre érvényesség-, üresgeometria- és duplikátumvizsgálatot ad hozzá; poligonokra átfedésvizsgálatot is. Az ismételt kattintás nem hozza létre újra a már felvett szabályokat.
- **Szabálykészletek:** automatikusan a projektbe kerülnek; a QGIS-projektet is mentsd el. Külön JSON-fájlba exportálhatók. A JSON betöltése lecseréli a panel aktuális szabálylistáját. Másik projektben az egyértelmű rétegnevek alapján újrakapcsolódnak; az azonos nevű vagy hiányzó rétegeket kézzel, a **Szerkesztés** gombbal rendeld hozzá.
- **Ellenőrzési kör:** teljes réteg, kijelölt elemek vagy a térképkivágattal metsződő elemek. A kijelölésnek minden aktív szabály forrásrétegén tartalmaznia kell elemet. A környező és referencia-elemeket minden esetben figyelembe veszi.
- **Hibák:** több szóból álló keresés, szabály szerinti szűrés és oszloponkénti rendezés. Kijelölt találatok térképi kiemelése; dupla kattintásra nagyítás; előző/következő navigáció. A **Forráselem kijelölése** az összehasonlított elemeket is kijelöli, ha van azonosítójuk.
- **Eredmények:** CSV, GeoPackage vagy ideiglenes QGIS-hibarétegek. A **Csak a szűrt találatok** kapcsoló az export és a réteglétrehozás körét is meghatározza.
- **Változások:** geometria-, elemszám- vagy szabályváltozás után a korábbi eredmény figyelmeztetést kap. A hibalista az ellenőrzéskori állapotot tartalmazza. Javítás után futtasd újra.

## Ellenőrzési szabályok

| Szabály | Működés |
| --- | --- |
| Érvényes geometria | GEOS szerinti geometriaérvényesség; ahol rendelkezésre áll, a hiba konkrét helyét jelzi. Az üres geometria külön szabály. |
| Nem lehet üres geometria | Hiányzó vagy üres geometria. Ezeknek nem mindig van térképen megjeleníthető helyük. |
| Csak egyrészes elemek | A ténylegesen több részből álló geometriák jelzése; egyrészes Multi-geometria megengedett. |
| Nem lehet duplikált geometria | Térben azonos geometriák, eltérő csúcspont-sorrend esetén is. Az attribútumokat nem hasonlítja össze. |
| Poligonok nem fedhetik egymást | Minden pozitív területű átfedés, a tartalmazást és az azonos poligonokat is beleértve. A közös határ nem hiba. |
| Nem lehet belső hézag | A teljes poligonréteg egyesítésének zárt belső lyukai. A külső határon nyitott üres területeket és a lefedendő terület ismerete nélkül értelmezhetetlen hiányokat nem keresi. A szándékos poligonlyukakat is jelzi. |
| Nem lehet szabad vonalvég | Másik vonalhoz vagy saját másik részhez nem csatlakozó vonalvégek. A másik vonal belsejéhez kapcsolódó T-csomópont megengedett, a zárt vonal megengedett. |
| Referencia-poligonoknak le kell fedniük | Pont, vonal vagy poligon teljes lefedettsége a referenciaréteg poligonjainak egyesítésével. A határra esés megengedett. A nem fedett geometriarészt adja vissza. |
| Nem fedheti a referenciaréteget | Pozitív területű átfedések két külön poligonréteg között. |

A vonalvégek toleranciája a **forrásréteg CRS-ének egységében** értendő; földrajzi CRS esetén fokban. A poligonátfedéseknél nincs területküszöb: a kis, pozitív területű szilánkokat is jelzi. Más CRS-ű referenciaréteget a forrás CRS-ébe transzformál. A térbeli ellenőrzések síkbeli GEOS-műveletek, a Z és M koordináták nem határozzák meg a kapcsolódást; íves geometriáknál a térbeli összehasonlításhoz szegmentálást használ.

## Export

**CSV:** UTF-8 BOM-mal, pontosvesszős elválasztóval, Excelben is olvasható magyar szövegekkel. Tartalmazza a szabály és a rétegek azonosítóját, az érintett elemek ID-ját, a hiba leírását, az eredeti CRS-t és WKT-geometriát, valamint a futás körét, UTC-kezdési idejét, teljességét, elavultságát és figyelmeztetéseit. A mezőidézés megőrzi a szövegbe ágyazott elválasztókat. A képletként értelmezhető szöveges értékek elé aposztróf kerül.

**GeoPackage:** az export térképi geometriái az aktuális térkép CRS-ében szerepelnek. Külön tábla készül a pont-, vonal-, poligon- és hely nélküli hibákhoz. Az eredeti geometria WKT-ként és a forrás CRS-e attribútumként is megmarad. A térképi geometria 2D és szegmentált. Vegyes GeometryCollection esetén egy hiba több táblában is szerepelhet azonos `error_id` mellett. A célfájl egy teljesen elkészült ideiglenes exporttal kerül lecserélésre; írási hiba esetén a korábbi fájl megmarad. Projektben megnyitott célfájl felülírását a bővítmény elutasítja; használj új fájlnevet.

Az ideiglenes hibarétegek memóriarétegek. Tartós tároláshoz exportáld őket GeoPackage-be.

## Futás és mérethatárok

A számítás megszakítható QGIS-háttérfeladat. A főszálon készített, saját tulajdonú `QgsVectorLayerFeatureSource` pillanatképekből dolgozik; a háttérszál nem használ élő projektet, térképi felületet vagy rétegobjektumot. Térbeli index csökkenti az elem-összehasonlítások számát. A kiválasztott forrásrétegek teljes geometriai környezetét beolvassa, ezért a kijelöléses vizsgálat is használhat jelentős memóriát.

Alapértelmezés: **10 000 hiba**, a panelen **100 000-ig** állítható. Rétegenként legfeljebb **250 000 elem** olvasható be. A korlát elérése, megszakítás, transzformációs hiba vagy kimaradó érvénytelen geometria **részleges eredményt** jelent, amit a felület és az export is jelez. Egy folyamatban lévő GEOS-művelet, például nagy poligonok egyesítése alatt a megszakítás a művelet befejeztével érvényesül. A projektből törölt függő réteg megszakítja a feladatot; a bővítmény kikapcsolásakor a feladat leválik a felületről és megszakítási kérést kap.

A bővítmény ellenőriz és navigál; a geometriák javítását a QGIS szerkesztőeszközeivel végezd el.

## Kipróbálható minta

Nyisd meg az `examples/topology-demo.qgz` projektet. A vele egy mappában lévő `topology-demo.gpkg` tartalmazza a mintarétegeket. A projektbe nyolc szabály van mentve; teljes rétegre futtatva **11 hibát** talál: duplikációt, átfedéseket, belső hézagot, szabad vonalvégeket, lefedettségi hibákat, önmetszést és üres geometriát. A mintaprojekt szándékosan hibás adatokat tartalmaz. A mintaszabályok külön JSON-ban is rendelkezésre állnak.

## Fejlesztés és tesztek

A teszteket a QGIS saját Pythonjával futtasd, ne a rendszer Pythonjával:

```powershell
.\tools\run_tests.ps1 -QgisRoot 'C:\Program Files\QGIS 3.44.9'
.\tools\run_tests.ps1 -QgisRoot 'C:\Program Files\QGIS 4.2.2'
python .\tools\package_plugin.py
```

A `tests/test_qgis.py` valódi PyQGIS/GEOS-integrációs teszteket futtat, a háttérfeladatot és a Qt-felületet is beleértve. A `tools/build_demo.py` a QGIS Pythonjával újragenerálja a mintaprojektet és a felület ellenőrzésére szolgáló képernyőképeket. A csomagolás nem igényel QGIS-t, és nem tartalmaz gyorsítótárakat vagy tesztfájlokat.

Verziónként 43 teszt, angol és magyar felülettel is ellenőrizve. A PowerShell-indító alapértelmezésben mindkét nyelvet teszteli; a `-Language en_US` vagy `-Language hu_HU` kapcsoló egy nyelvre szűkíti a futást. A `tools/verify_package.py` a kész ZIP-et a QGIS valódi bővítménybetöltőjével, ideiglenes mappában ellenőrzi, a felhasználói bővítményprofil módosítása nélkül.

API-források: [QGIS háttérfeladatok](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/tasks.html), [rétegválasztó](https://api.qgis.org/api/classQgsMapLayerComboBox.html), [geometriaműveletek](https://api.qgis.org/api/classQgsGeometry.html), [vektorfájl-export](https://api.qgis.org/api/classQgsVectorFileWriter.html).

Licenc: GNU GPL 3.0 vagy újabb, lásd `LICENSE`.
