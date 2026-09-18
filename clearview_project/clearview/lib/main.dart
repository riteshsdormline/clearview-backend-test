import 'dart:convert';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:uuid/uuid.dart';

import 'firebase_options.dart';
import 'models/processed_image.dart';
import 'services/analysis_service.dart';
import 'services/auth_service.dart';
import 'services/storage_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(const ClearviewApp());
}

class ClearviewApp extends StatelessWidget {
  const ClearviewApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'Clearview',
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff126b68)),
      scaffoldBackgroundColor: const Color(0xfff6f7f3),
    ),
    home: const SplashGate(),
  );
}

class SplashGate extends StatelessWidget {
  const SplashGate({super.key});

  @override
  Widget build(BuildContext context) => StreamBuilder<User?>(
    stream: AuthService().authStateChanges,
    builder: (context, snapshot) {
      if (snapshot.connectionState == ConnectionState.waiting) {
        return const SplashScreen();
      }
      return snapshot.data == null ? const LoginScreen() : const HomeScreen();
    },
  );
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) => const Scaffold(
    body: Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.visibility_rounded, size: 72, color: Color(0xff126b68)),
          SizedBox(height: 16),
          Text(
            'CLEARVIEW',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w800,
              letterSpacing: 3,
            ),
          ),
          Text('See what the image is hiding.'),
        ],
      ),
    ),
  );
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  bool loading = false;
  String? error;

  Future<void> login() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      await AuthService().signInWithGoogle();
    } catch (exception) {
      setState(() => error = exception.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Spacer(),
            const Icon(
              Icons.visibility_rounded,
              color: Color(0xff126b68),
              size: 64,
            ),
            const SizedBox(height: 28),
            const Text(
              'Clearview',
              style: TextStyle(fontSize: 42, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 12),
            Text(
              'Bring clarity to every image.',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const Spacer(),
            if (error != null)
              Text(error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: loading ? null : login,
              icon: const Icon(Icons.login),
              label: Text(loading ? 'Connecting...' : 'Continue with Google'),
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(56),
              ),
            ),
            const SizedBox(height: 20),
            const Center(
              child: Text('Your images stay private to your account.'),
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    ),
  );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final picker = ImagePicker();
  final analysis = AnalysisService();
  final storage = StorageService();
  List<ProcessedImage> history = [];
  bool loading = false;
  String? error;

  @override
  void initState() {
    super.initState();
    storage.loadLocal().then((items) {
      if (mounted) setState(() => history = items);
    });
  }

  Future<void> choose(ImageSource source) async {
    Navigator.pop(context);
    final picked = await picker.pickImage(
      source: source,
      imageQuality: 85,
      maxWidth: 1200,
      maxHeight: 1200,
    );
    if (picked == null) return;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final response = await analysis.analyze(File(picked.path));
      final image = ProcessedImage(
        id: const Uuid().v4(),
        createdAt: DateTime.now(),
        originalBase64: response['original_image_base64'] as String?,
        modifiedBase64: response['modified_image_base64'] as String,
        annotatedBase64: response['annotated_image_base64'] as String,
        report: Map<String, dynamic>.from(response['report'] as Map),
      );
      await storage.save(image);
      if (!mounted) return;
      setState(() => history = [image, ...history].take(20).toList());
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => EditorScreen(image: image)),
      );
    } catch (exception) {
      if (mounted) setState(() => error = exception.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  void openPicker() => showModalBottomSheet<void>(
    context: context,
    builder:
        (_) => SafeArea(
          child: Wrap(
            children: [
              ListTile(
                leading: const Icon(Icons.camera_alt),
                title: const Text('Take a photo'),
                onTap: () => choose(ImageSource.camera),
              ),
              ListTile(
                leading: const Icon(Icons.photo_library),
                title: const Text('Choose from gallery'),
                onTap: () => choose(ImageSource.gallery),
              ),
            ],
          ),
        ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text(
        'Clearview',
        style: TextStyle(fontWeight: FontWeight.w800),
      ),
      actions: [
        IconButton(
          onPressed: () => AuthService().signOut(),
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
    body: RefreshIndicator(
      onRefresh: () async => setState(() {}),
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            'Visual condition analysis',
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(color: const Color(0xff126b68)),
          ),
          const SizedBox(height: 8),
          Text(
            'See what the image is hiding.',
            style: Theme.of(
              context,
            ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 22),
          InkWell(
            onTap: loading ? null : openPicker,
            borderRadius: BorderRadius.circular(24),
            child: Container(
              height: 190,
              decoration: BoxDecoration(
                color: const Color(0xffd9ebe4),
                borderRadius: BorderRadius.circular(24),
              ),
              child: Center(
                child:
                    loading
                        ? const CircularProgressIndicator()
                        : const Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.add_a_photo_outlined, size: 48),
                            SizedBox(height: 12),
                            Text(
                              'Upload an image',
                              style: TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            Text('Camera or gallery'),
                          ],
                        ),
              ),
            ),
          ),
          if (error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 30),
          const Text(
            'Recent inspections',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 12),
          if (history.isEmpty)
            const Text('Your processed images will appear here.'),
          ...history.map(
            (image) => Card(
              child: ListTile(
                contentPadding: const EdgeInsets.all(10),
                leading: ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.memory(
                    base64Decode(image.modifiedBase64),
                    width: 64,
                    height: 64,
                    fit: BoxFit.cover,
                  ),
                ),
                title: Text(
                  '${image.report['num_objects_detected'] ?? 0} objects detected',
                ),
                subtitle: Text(
                  '${image.createdAt.day}/${image.createdAt.month}/${image.createdAt.year}',
                ),
                onTap:
                    () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => EditorScreen(image: image),
                      ),
                    ),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () async {
                    await storage.delete(image.id);
                    setState(
                      () => history.removeWhere((item) => item.id == image.id),
                    );
                  },
                ),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

class EditorScreen extends StatefulWidget {
  const EditorScreen({super.key, required this.image});
  final ProcessedImage image;

  @override
  State<EditorScreen> createState() => _EditorScreenState();
}

class _EditorScreenState extends State<EditorScreen> {
  double brightness = 0;
  double saturation = 1;
  double warmth = 0;
  bool annotated = false;

  Future<void> share() async {
    final directory = await getTemporaryDirectory();
    final bytes = base64Decode(
      annotated ? widget.image.annotatedBase64 : widget.image.modifiedBase64,
    );
    final file = File('${directory.path}/clearview-${widget.image.id}.jpg');
    await file.writeAsBytes(bytes);
    await Share.shareXFiles([XFile(file.path)], text: 'Clearview inspection');
  }

  @override
  Widget build(BuildContext context) {
    final imageData =
        annotated ? widget.image.annotatedBase64 : widget.image.modifiedBase64;
    final detections = (widget.image.report['detections'] as List?) ?? [];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Edit inspection'),
        actions: [
          IconButton(onPressed: share, icon: const Icon(Icons.ios_share)),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: ColorFiltered(
              colorFilter: ColorFilter.matrix([
                1 + brightness,
                0,
                0,
                0,
                0,
                0,
                saturation,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
              ]),
              child: Image.memory(base64Decode(imageData), fit: BoxFit.cover),
            ),
          ),
          const SizedBox(height: 20),
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Enhanced')),
              ButtonSegment(value: true, label: Text('Annotated')),
            ],
            selected: {annotated},
            onSelectionChanged:
                (value) => setState(() => annotated = value.first),
          ),
          const SizedBox(height: 20),
          adjustment(
            'Brightness',
            brightness,
            -0.4,
            0.4,
            (value) => setState(() => brightness = value),
          ),
          adjustment(
            'Saturation',
            saturation,
            0.5,
            1.5,
            (value) => setState(() => saturation = value),
          ),
          adjustment(
            'Warmth',
            warmth,
            -0.3,
            0.3,
            (value) => setState(() => warmth = value),
          ),
          const SizedBox(height: 12),
          Text(
            '${detections.length} detections reviewed',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          ...detections.map(
            (item) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.circle, size: 12, color: Colors.orange),
              title: Text('${item['best_guess']}'),
              subtitle: Text(
                '${item['severity']} · score ${item['scuff_score']}',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget adjustment(
    String label,
    double value,
    double min,
    double max,
    ValueChanged<double> onChanged,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [Text(label), Text(value.toStringAsFixed(2))],
      ),
      Slider(value: value, min: min, max: max, onChanged: onChanged),
    ],
  );
}
