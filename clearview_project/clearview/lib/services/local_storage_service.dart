import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/processed_image.dart';

class LocalStorageService {
  static const _localKey = 'processed_images_metadata';

  Future<String> get _localPath async {
    final directory = await getApplicationDocumentsDirectory();
    return directory.path;
  }

  Future<List<ProcessedImage>> loadHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final metadataJson = prefs.getStringList(_localKey) ?? [];
    
    return metadataJson.map((jsonStr) {
      return ProcessedImage.fromJson(jsonDecode(jsonStr) as Map<String, dynamic>);
    }).toList();
  }

  Future<void> saveImage(ProcessedImage image) async {
    final path = await _localPath;
    
    // Save images as files instead of keeping them in memory/SharedPreferences
    final modifiedFile = File('$path/${image.id}_modified.jpg');
    await modifiedFile.writeAsBytes(base64Decode(image.modifiedBase64));

    final annotatedFile = File('$path/${image.id}_annotated.jpg');
    await annotatedFile.writeAsBytes(base64Decode(image.annotatedBase64));

    // Create a version of the object without the huge base64 strings for the metadata index
    final metadata = {
      'id': image.id,
      'createdAt': image.createdAt.toIso8601String(),
      'report': image.report,
      // We store the paths instead of data to keep SharedPreferences light
      'modifiedPath': modifiedFile.path,
      'annotatedPath': annotatedFile.path,
    };

    final prefs = await SharedPreferences.getInstance();
    final history = prefs.getStringList(_localKey) ?? [];
    history.insert(0, jsonEncode(metadata));
    
    // Keep only last 20
    if (history.length > 20) history.removeRange(20, history.length);
    
    await prefs.setStringList(_localKey, history);
  }

  Future<void> deleteImage(String id) async {
    final path = await _localPath;
    try {
      await File('$path/${id}_modified.jpg').delete();
      await File('$path/${id}_annotated.jpg').delete();
    } catch (_) {}

    final prefs = await SharedPreferences.getInstance();
    final history = prefs.getStringList(_localKey) ?? [];
    history.removeWhere((item) => jsonDecode(item)['id'] == id);
    await prefs.setStringList(_localKey, history);
  }
}
