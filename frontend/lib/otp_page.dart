import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'marine_profile_page.dart';

class OTPPage extends StatefulWidget {
  final String name;
  final String email;
  final String password;

  const OTPPage({
    super.key,
    required this.name,
    required this.email,
    required this.password,
  });

  @override
  State<OTPPage> createState() => _OTPPageState();
}

class _OTPPageState extends State<OTPPage> {
  final otpController = TextEditingController();

  bool loading = false;

  static const String apiBaseUrl = 'https://marineintelligence.onrender.com';

  @override
  void dispose() {
    otpController.dispose();
    super.dispose();
  }

  Future<void> verifyOTP() async {
    final otp = otpController.text.trim();

    if (otp.length != 6) {
      showMessage('Please enter the 6-digit OTP.');
      return;
    }

    setState(() {
      loading = true;
    });

    try {
      // ------------------------------------------
      // VERIFY OTP
      // ------------------------------------------

      final verifyResponse = await http
          .post(
            Uri.parse('$apiBaseUrl/register/verify-otp'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'email': widget.email, 'otp': otp}),
          )
          .timeout(const Duration(seconds: 20));

      final verifyData = jsonDecode(verifyResponse.body);

      if (verifyResponse.statusCode < 200 || verifyResponse.statusCode >= 300) {
        final message =
            verifyData['detail'] ?? verifyData['message'] ?? 'Invalid OTP.';

        showMessage(message.toString());
        return;
      }

      // ------------------------------------------
      // CREATE ACCOUNT AFTER OTP VERIFICATION
      // ------------------------------------------

      final registerResponse = await http
          .post(
            Uri.parse('$apiBaseUrl/register'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'name': widget.name,
              'email': widget.email,
              'password': widget.password,
            }),
          )
          .timeout(const Duration(seconds: 20));

      final registerData = jsonDecode(registerResponse.body);

      if (registerResponse.statusCode >= 200 &&
          registerResponse.statusCode < 300) {
        final token = registerData['access_token'];

        if (token == null) {
          showMessage(
            'Account created, but authentication token was not received.',
          );
          return;
        }
        if (!mounted) return;

        if (!mounted) return;

        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => MarineProfilePage(
              name: widget.name,
              email: widget.email,
              token: token,
            ),
          ),
        );
      } else {
        final message =
            registerData['detail'] ??
            registerData['message'] ??
            'Registration failed.';

        showMessage(message.toString());
      }
    } catch (e) {
      showMessage('Unable to connect to server. Please try again.');
    } finally {
      if (mounted) {
        setState(() {
          loading = false;
        });
      }
    }
  }

  void showMessage(String message) {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  @override
  Widget build(BuildContext context) {
    const dark = Color(0xFF183B3D);
    const teal = Color(0xFF285B5B);
    const bg = Color(0xFFF3F6F1);

    return Scaffold(
      backgroundColor: bg,

      appBar: AppBar(
        backgroundColor: bg,
        elevation: 0,
        foregroundColor: dark,

        title: const Text(
          'Verify email',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),

      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),

          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,

            children: [
              const SizedBox(height: 25),

              const Icon(Icons.mark_email_read_outlined, size: 58, color: teal),

              const SizedBox(height: 22),

              const Text(
                'Verify your email',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w700,
                  color: dark,
                ),
              ),

              const SizedBox(height: 10),

              Text(
                'We sent a 6-digit verification code to:',
                style: TextStyle(fontSize: 14, color: Colors.grey.shade600),
              ),

              const SizedBox(height: 5),

              Text(
                widget.email,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: dark,
                ),
              ),

              const SizedBox(height: 30),

              TextField(
                controller: otpController,
                keyboardType: TextInputType.number,

                maxLength: 6,

                textAlign: TextAlign.center,

                style: const TextStyle(
                  fontSize: 25,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 8,
                ),

                decoration: InputDecoration(
                  counterText: '',
                  hintText: '------',

                  filled: true,
                  fillColor: Colors.white,

                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(18),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),

              const SizedBox(height: 25),

              SizedBox(
                width: double.infinity,
                height: 54,

                child: FilledButton(
                  onPressed: loading ? null : verifyOTP,

                  style: FilledButton.styleFrom(
                    backgroundColor: teal,

                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(18),
                    ),
                  ),

                  child: loading
                      ? const SizedBox(
                          width: 23,
                          height: 23,

                          child: CircularProgressIndicator(
                            strokeWidth: 2.5,
                            color: Colors.white,
                          ),
                        )
                      : const Text(
                          'VERIFY & CREATE ACCOUNT',
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.8,
                          ),
                        ),
                ),
              ),

              const SizedBox(height: 15),

              Center(
                child: Text(
                  'OTP is valid for 5 minutes.',
                  style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
