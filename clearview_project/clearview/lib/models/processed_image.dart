class ProcessedImage {
  const ProcessedImage({
    required this.id,
    required this.createdAt,
    required this.modifiedBase64,
    required this.annotatedBase64,
    required this.report,
    this.originalBase64,
  });

  final String id;
  final DateTime createdAt;
  final String modifiedBase64;
  final String annotatedBase64;
  final String? originalBase64;
  final Map<String, dynamic> report;

  Map<String, dynamic> toJson() => {
    'id': id,
    'createdAt': createdAt.toIso8601String(),
    'modifiedBase64': modifiedBase64,
    'annotatedBase64': annotatedBase64,
    'originalBase64': originalBase64,
    'report': report,
  };

  factory ProcessedImage.fromJson(Map<String, dynamic> json) => ProcessedImage(
    id: json['id'] as String,
    createdAt: DateTime.parse(json['createdAt'] as String),
    modifiedBase64: json['modifiedBase64'] as String,
    annotatedBase64: json['annotatedBase64'] as String,
    originalBase64: json['originalBase64'] as String?,
    report: Map<String, dynamic>.from(json['report'] as Map),
  );
}
