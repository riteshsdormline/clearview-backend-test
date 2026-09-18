import 'dart:convert';
import 'dart:io';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/processed_image.dart';

class StorageService {
  static const _localKey = 'processed_images_v2';
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Future<String> get _localPath async {
    final directory = await getApplicationDocumentsDirectory();
    return directory.path;
  }

  Future<List<ProcessedImage>> loadLocal() async {
    final prefs = await SharedPreferences.getInstance();
    final metadataList = prefs.getStringList(_localKey) ?? [];
    
    List<ProcessedImage> images = [];
    for (var jsonStr in metadataList) {
      try {
        final data = jsonDecode(jsonStr) as Map<String, dynamic>;
        // Load image data from local files instead of storing base64 in SharedPreferences
        final modifiedFile = File(data['modifiedPath'] as String);
        final annotatedFile = File(data['annotatedPath'] as String);
        
        if (await modifiedFile.exists() && await annotatedFile.exists()) {
          images.add(ProcessedImage(
            id: data['id'] as String,
            createdAt: DateTime.parse(data['createdAt'] as String),
            modifiedBase64: base64Encode(await modifiedFile.readAsBytes()),
            annotatedBase64: base64Encode(await annotatedFile.readAsBytes()),
            report: Map<String, dynamic>.from(data['report'] as Map),
          ));
        }
      } catch (e) {
        debugPrint('Error loading image from local storage: $e');
      }
    }
    return images;
  }

  Future<void> save(ProcessedImage image) async {
    final path = await _localPath;
    
    // 1. Save images to local files (Free)
    final modifiedFile = File('$path/${image.id}_mod.jpg');
    await modifiedFile.writeAsBytes(base64Decode(image.modifiedBase64));

    final annotatedFile = File('$path/${image.id}_ann.jpg');
    await annotatedFile.writeAsBytes(base64Decode(image.annotatedBase64));

    // 2. Save metadata locally (Free)
    final prefs = await SharedPreferences.getInstance();
    final metadataList = prefs.getStringList(_localKey) ?? [];
    
    final metadata = {
      'id': image.id,
      'createdAt': image.createdAt.toIso8601String(),
      'report': image.report,
      'modifiedPath': modifiedFile.path,
      'annotatedPath': annotatedFile.path,
    };
    
    metadataList.insert(0, jsonEncode(metadata));
    if (metadataList.length > 20) metadataList.removeRange(20, metadataList.length);
    await prefs.setStringList(_localKey, metadataList);

    // 3. Save only METADATA (report) to Firestore (Very cheap/Free tier)
    // We stopped uploading the image bytes to Firebase Storage to save money.
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return;
    
    try {
      await _firestore
          .collection('users')
          .doc(user.uid)
          .collection('inspections')
          .doc(image.id)
          .set({
            'createdAt': Timestamp.fromDate(image.createdAt),
            'report': image.report,
            'hasLocalImages': true,
          });
    } catch (e) {
      debugPrint('Error syncing metadata to Firestore: $e');
    }
  }

  Future<void> delete(String id) async {
    final path = await _localPath;
    try {
      await File('$path/${id}_mod.jpg').delete();
      await File('$path/${id}_ann.jpg').delete();
    } catch (_) {}

    final prefs = await SharedPreferences.getInstance();
    final metadataList = prefs.getStringList(_localKey) ?? [];
    metadataList.removeWhere((item) => jsonDecode(item)['id'] == id);
    await prefs.setStringList(_localKey, metadataList);

    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return;
    
    try {
      await _firestore
          .collection('users')
          .doc(user.uid)
          .collection('inspections')
          .doc(id)
          .delete();
    } catch (e) {
      debugPrint('Error deleting metadata from Firestore: $e');
    }
  }
}
