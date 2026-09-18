class ApiConfig {
  static const bool useLocalBackend = false;

  static const String productionUrl = 'https://clearview-backend-0uox.onrender.com';
  static const String localUrl = 'http://10.0.2.2:8000'; // Android emulator localhost

  static String get baseUrl => useLocalBackend ? localUrl : productionUrl;
  static String get analyzeEndpoint => '$baseUrl/analyze';
}
