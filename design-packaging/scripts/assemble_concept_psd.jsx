#target photoshop

/*
 * Assemble a five-group packaging concept PSD entirely offline in Photoshop 2023.
 * Input: element-manifest.json plus full-canvas PNG element files.
 * Output: layered PSD, Photoshop recomposite, difference image, fidelity report,
 *         and reopen verification report.
 */

(function () {
    var EXPECTED_GROUPS = ["01_BG", "02_MAIN", "03_AUX", "04_LABEL", "05_TYPE"];
    var oldDialogs = app.displayDialogs;
    var oldUnits = app.preferences.rulerUnits;
    app.displayDialogs = DialogModes.NO;
    app.preferences.rulerUnits = Units.PIXELS;

    function fail(message) {
        throw new Error(message);
    }

    function readText(file) {
        if (!file.open("r")) {
            fail("无法打开文件：" + file.fsName);
        }
        file.encoding = "UTF8";
        var content = file.read();
        file.close();
        return content;
    }

    function parseJSON(text) {
        if (typeof JSON !== "undefined" && JSON.parse) {
            return JSON.parse(text);
        }
        return eval("(" + text + ")");
    }

    function quoteJSON(text) {
        return '"' + String(text)
            .replace(/\\/g, "\\\\")
            .replace(/\"/g, '\\"')
            .replace(/\r/g, "\\r")
            .replace(/\n/g, "\\n")
            .replace(/\t/g, "\\t") + '"';
    }

    function stringifyJSON(value, depth) {
        depth = depth || 0;
        if (value === null) {
            return "null";
        }
        var type = typeof value;
        if (type === "string") {
            return quoteJSON(value);
        }
        if (type === "number" || type === "boolean") {
            return String(value);
        }
        if (value instanceof Array) {
            var arrayItems = [];
            for (var i = 0; i < value.length; i++) {
                arrayItems.push(stringifyJSON(value[i], depth + 1));
            }
            return "[" + arrayItems.join(",") + "]";
        }
        var objectItems = [];
        for (var key in value) {
            if (value.hasOwnProperty(key)) {
                objectItems.push(quoteJSON(key) + ":" + stringifyJSON(value[key], depth + 1));
            }
        }
        return "{" + objectItems.join(",") + "}";
    }

    function writeJSON(file, data) {
        file.encoding = "UTF8";
        file.lineFeed = "Unix";
        if (!file.open("w")) {
            fail("无法写入文件：" + file.fsName);
        }
        file.write(stringifyJSON(data));
        file.close();
    }

    function safeName(value, fallback) {
        var text = String(value || fallback);
        text = text.replace(/[\\\/:*?\"<>|\s]+/g, "-");
        text = text.replace(/^-+|-+$/g, "");
        return text || fallback;
    }

    function relativeFile(baseFolder, relativePath) {
        if (!relativePath || /^([A-Za-z]:|\\\\|\/)/.test(relativePath)) {
            fail("清单必须使用项目目录内的相对路径：" + relativePath);
        }
        var file = new File(baseFolder.fsName + "/" + relativePath);
        if (!file.exists) {
            fail("文件不存在：" + file.fsName);
        }
        return file;
    }

    function relativeFolder(baseFolder, relativePath) {
        if (!relativePath || /^([A-Za-z]:|\\\\|\/)/.test(relativePath)) {
            fail("输出目录必须使用项目目录内的相对路径：" + relativePath);
        }
        var folder = new Folder(baseFolder.fsName + "/" + relativePath);
        if (!folder.exists && !folder.create()) {
            fail("无法创建输出目录：" + folder.fsName);
        }
        return folder;
    }

    function assertManifest(manifest) {
        if (manifest.schema_version !== "1.0") {
            fail("schema_version 必须为 1.0。请先运行 Python 检查器。");
        }
        if (!manifest.canvas || manifest.canvas.concept_only !== true) {
            fail("该脚本只装配 concept_only=true 的概念 PSD。");
        }
        if (manifest.canvas.color_mode !== "RGB") {
            fail("概念 PSD 当前只允许 RGB。生产 CMYK 必须按印厂参数转换。");
        }
        if (!manifest.groups || manifest.groups.length !== EXPECTED_GROUPS.length) {
            fail("清单必须包含五个固定组。");
        }
        for (var i = 0; i < EXPECTED_GROUPS.length; i++) {
            if (manifest.groups[i].name !== EXPECTED_GROUPS[i]) {
                fail("组顺序错误，必须为：" + EXPECTED_GROUPS.join(", "));
            }
            for (var e = 0; e < manifest.groups[i].elements.length; e++) {
                var element = manifest.groups[i].elements[e];
                if (element.isolation_mode === "layer-mask") {
                    fail(
                        "当前可选自动脚本不装配 layer-mask：" + element.id +
                        "。请在 Photoshop 中手工加载该元素的黑白蒙版。"
                    );
                }
            }
        }
    }

    function toNumber(value) {
        return Number(value.as("px"));
    }

    function importAsSmartObject(sourceFile, targetDoc, group, layerName, width, height) {
        var sourceDoc = app.open(sourceFile);
        if (toNumber(sourceDoc.width) !== width || toNumber(sourceDoc.height) !== height) {
            sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
            fail("元素尺寸不一致：" + sourceFile.fsName);
        }
        sourceDoc.activeLayer.duplicate(targetDoc, ElementPlacement.PLACEATBEGINNING);
        sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = targetDoc;
        var layer = targetDoc.activeLayer;
        layer.name = layerName;
        try {
            executeAction(stringIDToTypeID("newPlacedLayer"), undefined, DialogModes.NO);
        } catch (conversionError) {
            fail("无法把元素转换为智能对象：" + layerName + "\n" + conversionError.message);
        }
        layer = targetDoc.activeLayer;
        layer.name = layerName;
        if (group !== null) {
            layer.move(group, ElementPlacement.INSIDE);
        }
        return layer;
    }

    function exportPNG(document, file) {
        app.activeDocument = document;
        var options = new ExportOptionsSaveForWeb();
        options.format = SaveDocumentType.PNG;
        options.PNG8 = false;
        options.transparency = true;
        options.interlaced = false;
        options.includeProfile = true;
        document.exportDocument(file, ExportType.SAVEFORWEB, options);
    }

    function savePSD(document, file) {
        app.activeDocument = document;
        var options = new PhotoshopSaveOptions();
        options.layers = true;
        options.embedColorProfile = true;
        options.maximizeCompatibility = true;
        document.saveAs(file, options, false, Extension.LOWERCASE);
    }

    function findGroup(document, name) {
        for (var i = 0; i < document.layerSets.length; i++) {
            if (document.layerSets[i].name === name) {
                return document.layerSets[i];
            }
        }
        return null;
    }

    function buildFidelityReport(manifest) {
        var counts = {
            "source-extracted": 0,
            "occlusion-completed": 0,
            "upscaled-rebuilt": 0,
            "retyped": 0,
            "manual-redraw": 0
        };
        var elements = [];
        var lowConfidence = 0;
        var requiresConfirmation = false;
        for (var g = 0; g < manifest.groups.length; g++) {
            var group = manifest.groups[g];
            for (var e = 0; e < group.elements.length; e++) {
                var element = group.elements[e];
                if (counts[element.source_method] === undefined) {
                    counts[element.source_method] = 0;
                }
                counts[element.source_method]++;
                if (element.confidence === "low") {
                    lowConfidence++;
                    if (element.important === true) {
                        requiresConfirmation = true;
                    }
                }
                elements.push({
                    id: element.id,
                    name: element.name,
                    group: group.name,
                    file: element.file,
                    source_method: element.source_method,
                    confidence: element.confidence,
                    occlusion: element.occlusion,
                    important: element.important === true,
                    notes: element.notes || ""
                });
            }
        }
        return {
            schema_version: "1.0",
            project: manifest.project,
            face: manifest.face,
            concept_only: true,
            reference: manifest.reference,
            summary: {
                element_count: elements.length,
                source_extracted: counts["source-extracted"],
                occlusion_completed: counts["occlusion-completed"],
                upscaled_rebuilt: counts["upscaled-rebuilt"],
                retyped: counts["retyped"],
                manual_redraw: counts["manual-redraw"],
                low_confidence: lowConfidence,
                requires_user_confirmation: requiresConfirmation
            },
            elements: elements,
            limitations: [
                "完全被遮挡的原始像素无法精确恢复，只能合理补全。",
                "没有真实尺寸、材料和印厂参数时，本文件不是生产尺寸。"
            ]
        };
    }

    function verifyReopened(document, manifest, psdFile) {
        var errors = [];
        var width = Number(manifest.canvas.width_px);
        var height = Number(manifest.canvas.height_px);
        if (toNumber(document.width) !== width || toNumber(document.height) !== height) {
            errors.push("PSD 画布尺寸不符合清单。");
        }
        if (document.artLayers.length !== 0) {
            errors.push("存在未归组的顶层像素图层。");
        }
        var details = [];
        for (var i = 0; i < EXPECTED_GROUPS.length; i++) {
            var name = EXPECTED_GROUPS[i];
            var group = findGroup(document, name);
            if (group === null) {
                errors.push("缺少顶层组：" + name);
                continue;
            }
            var expectedCount = manifest.groups[i].elements.length;
            var actualCount = group.artLayers.length + group.layerSets.length;
            if (actualCount !== expectedCount) {
                errors.push(name + " 元素数为 " + actualCount + "，应为 " + expectedCount + "。");
            }
            var names = [];
            for (var a = 0; a < group.artLayers.length; a++) {
                names.push(group.artLayers[a].name);
            }
            details.push({name: name, element_count: actualCount, elements: names});
        }
        return {
            valid: errors.length === 0,
            psd: psdFile.fsName,
            photoshop_version: app.version,
            reopened: true,
            size: {width_px: toNumber(document.width), height_px: toNumber(document.height)},
            groups: details,
            errors: errors
        };
    }

    try {
        // Normal use opens a file picker. PACKAGING_MANIFEST is an optional
        // local-only automation hook used for repeatable Photoshop QA.
        var manifestOverride = $.getenv("PACKAGING_MANIFEST");
        var manifestFile = manifestOverride
            ? new File(manifestOverride)
            : File.openDialog("选择 element-manifest.json", "JSON:*.json");
        if (manifestFile === null) {
            return;
        }
        if (!manifestFile.exists) {
            fail("清单文件不存在：" + manifestFile.fsName);
        }
        var manifest = parseJSON(readText(manifestFile));
        assertManifest(manifest);

        var baseFolder = manifestFile.parent;
        var referenceFile = relativeFile(baseFolder, manifest.reference);
        var outputFolder = relativeFolder(
            baseFolder,
            manifest.output && manifest.output.directory ? manifest.output.directory : "output"
        );
        var width = Number(manifest.canvas.width_px);
        var height = Number(manifest.canvas.height_px);
        var resolution = Number(manifest.canvas.resolution_ppi);
        if (!(width > 0 && height > 0 && resolution > 0)) {
            fail("画布宽、高和分辨率必须为正数。");
        }

        var project = safeName(manifest.project, "project");
        var face = safeName(manifest.face, "face");
        var version = safeName(manifest.version, "v001");
        var baseName = project + "_" + face;
        var psdFile = new File(outputFolder.fsName + "/" + baseName + "_concept_" + version + ".psd");
        var recompositeFile = new File(outputFolder.fsName + "/" + baseName + "_recomposite-photoshop.png");
        var differenceFile = new File(outputFolder.fsName + "/" + baseName + "_difference-photoshop.png");
        var fidelityFile = new File(outputFolder.fsName + "/layer-fidelity-report.json");
        var verificationFile = new File(outputFolder.fsName + "/photoshop-verification.json");

        var document = app.documents.add(
            width,
            height,
            resolution,
            baseName + "_concept_" + version,
            NewDocumentMode.RGB,
            DocumentFill.TRANSPARENT,
            1.0,
            BitsPerChannelType.EIGHT
        );

        var groupMap = {};
        for (var g = 0; g < manifest.groups.length; g++) {
            var manifestGroup = manifest.groups[g];
            var layerSet = document.layerSets.add();
            layerSet.name = manifestGroup.name;
            groupMap[manifestGroup.name] = layerSet;
            for (var e = 0; e < manifestGroup.elements.length; e++) {
                var element = manifestGroup.elements[e];
                var sourceFile = relativeFile(baseFolder, element.file);
                importAsSmartObject(
                    sourceFile,
                    document,
                    layerSet,
                    element.id + "__" + (element.name || element.id),
                    width,
                    height
                );
            }
        }

        exportPNG(document, recompositeFile);

        var differenceDocument = document.duplicate(baseName + "_difference", false);
        app.activeDocument = differenceDocument;
        var referenceLayer = importAsSmartObject(
            referenceFile,
            differenceDocument,
            null,
            "APPROVED_REFERENCE_DIFFERENCE",
            width,
            height
        );
        referenceLayer.blendMode = BlendMode.DIFFERENCE;
        exportPNG(differenceDocument, differenceFile);
        differenceDocument.close(SaveOptions.DONOTSAVECHANGES);

        app.activeDocument = document;
        savePSD(document, psdFile);
        writeJSON(fidelityFile, buildFidelityReport(manifest));
        document.close(SaveOptions.SAVECHANGES);

        var reopened = app.open(psdFile);
        var verification = verifyReopened(reopened, manifest, psdFile);
        writeJSON(verificationFile, verification);
        if (!verification.valid) {
            alert("PSD 已生成，但重新打开核验失败：\n" + verification.errors.join("\n"));
        } else {
            alert(
                "概念 PSD 已生成并重新打开核验通过。\n\n" +
                psdFile.fsName + "\n\n" +
                "请人工检查重组预览、差异图和低可信元素。"
            );
        }
    } catch (error) {
        alert("包装概念 PSD 装配失败：\n" + error.message + (error.line ? "\n行号：" + error.line : ""));
    } finally {
        app.displayDialogs = oldDialogs;
        app.preferences.rulerUnits = oldUnits;
    }
}());
