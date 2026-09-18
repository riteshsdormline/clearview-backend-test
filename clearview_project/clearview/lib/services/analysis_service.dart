import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'api_config.dart';

class AnalysisService {
  /// Pings the backend to wake it up if it's sleeping (Hugging Face Spaces).
  Future<void> wakeUp() async {
    try {
      final url = ApiConfig.baseUrl;
      await http.get(Uri.parse('$url/health')).timeout(const Duration(seconds: 5));
    } catch (_) {
      // Silently ignore wake-up failures
    }
  }

  Future<Map<String, dynamic>> analyze(
    File image, {
    double threshold = 0.65,
  }) async {
    print('Starting analysis for: ${image.path}');
    print('Using endpoint: ${ApiConfig.analyzeEndpoint}');
    
    try {
      final request = http.MultipartRequest('POST', Uri.parse(ApiConfig.analyzeEndpoint));
      request.files.add(await http.MultipartFile.fromPath('image', image.path));
      request.fields['threshold'] = threshold.toString();
      request.fields['detector'] = 'voc';
      
      print('Sending request...');
      final response = await request.send().timeout(const Duration(seconds: 60));
      print('Response status: ${response.statusCode}');
      
      final body = await response.stream.bytesToString();
      
      if (response.statusCode == 502 || response.statusCode == 504) {
        throw Exception('The backend is currently waking up or overloaded. Please try again in 1 minute.');
      }

      print('Response body preview: ${body.substring(0, body.length > 100 ? 100 : body.length)}');
      
      Map<String, dynamic> data;
      try {
        data = jsonDecode(body) as Map<String, dynamic>;
      } catch (e) {
        print('JSON Decode error: $e');
        throw Exception(
          'The analysis service returned an invalid response (${response.statusCode}).',
        );
      }
      
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception(
          data['detail'] ??
              data['error'] ??
              'Analysis failed (${response.statusCode}).',
        );
      }
      return data;
    } catch (e) {
      print('AnalysisService error: $e');
      rethrow;
    }
  }
}
