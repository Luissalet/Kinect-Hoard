using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Speech.AudioFormat;
using System.Speech.Recognition;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace KinectHoard.App
{
    internal static class SpeechCommands
    {
        internal static int RecognizeFile(string wavePath, string outputPath, string grammarPath)
        {
            try
            {
                var grammar = ReadGrammar(grammarPath);
                byte[] pcm = ReadPcm16(wavePath);
                var events = new List<Dictionary<string, object>>();
                int rejected = 0;
                Exception completionError = null;
                using (var completed = new ManualResetEvent(false))
                using (var input = new MemoryStream(pcm, false))
                using (var engine = CreateEngine(grammar.Item1, grammar.Item2))
                {
                    engine.SetInputToAudioStream(input, new SpeechAudioFormatInfo(16000, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
                    engine.SpeechRecognized += (sender, args) =>
                    {
                        var result = args.Result;
                        lock (events)
                            events.Add(new Dictionary<string, object> {
                                { "text", result.Text },
                                { "confidence", result.Confidence },
                                { "audio_position_seconds", result.Audio == null ? 0 : result.Audio.AudioPosition.TotalSeconds }
                            });
                    };
                    engine.SpeechRecognitionRejected += (sender, args) => Interlocked.Increment(ref rejected);
                    engine.RecognizeCompleted += (sender, args) => { completionError = args.Error; completed.Set(); };
                    engine.RecognizeAsync(RecognizeMode.Multiple);
                    int waitMs = Math.Min(180000, (int)(pcm.Length / 32000.0 * 2000 + 15000));
                    if (!completed.WaitOne(waitMs))
                    {
                        engine.RecognizeAsyncCancel();
                        throw new TimeoutException("El motor de voz no terminó de procesar el audio.");
                    }
                    if (completionError != null) throw completionError;
                }
                var resultJson = new Dictionary<string, object> {
                    { "format", "KINECT_HOARD_SPEECH_1" },
                    { "culture", grammar.Item1.Name },
                    { "grammar", Path.GetFileName(grammarPath) },
                    { "audio_seconds", pcm.Length / 32000.0 },
                    { "recognized", events },
                    { "rejected", rejected }
                };
                File.WriteAllText(outputPath, new JavaScriptSerializer().Serialize(resultJson), Encoding.UTF8);
                return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine("Voz: " + ex.GetBaseException().Message); return 1; }
        }

        private static SpeechRecognitionEngine CreateEngine(CultureInfo culture, string[] phrases)
        {
            var recognizer = SpeechRecognitionEngine.InstalledRecognizers()
                .FirstOrDefault(item => item.Culture.Name.Equals(culture.Name, StringComparison.OrdinalIgnoreCase));
            if (recognizer == null) throw new InvalidOperationException("No hay motor de voz instalado para " + culture.Name + ".");
            var engine = new SpeechRecognitionEngine(recognizer);
            try
            {
                var builder = new GrammarBuilder { Culture = culture };
                builder.Append(new Choices(phrases));
                engine.LoadGrammar(new Grammar(builder) { Name = "KinectHoard.commands" });
                return engine;
            }
            catch { engine.Dispose(); throw; }
        }

        private static Tuple<CultureInfo, string[]> ReadGrammar(string path)
        {
            if (!File.Exists(path)) throw new FileNotFoundException("Falta la gramática de comandos.", path);
            var phrases = new List<string>();
            CultureInfo culture = CultureInfo.GetCultureInfo("es-ES");
            foreach (string raw in File.ReadAllLines(path, Encoding.UTF8))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
                if (line.StartsWith("culture=", StringComparison.OrdinalIgnoreCase))
                    culture = CultureInfo.GetCultureInfo(line.Substring(8).Trim());
                else phrases.Add(line);
            }
            string[] commands = phrases.Distinct(StringComparer.CurrentCultureIgnoreCase).ToArray();
            if (commands.Length == 0) throw new InvalidDataException("La gramática no contiene comandos.");
            return Tuple.Create(culture, commands);
        }

        private static byte[] ReadPcm16(string path)
        {
            using (var reader = new BinaryReader(File.OpenRead(path)))
            {
                if (new string(reader.ReadChars(4)) != "RIFF") throw new InvalidDataException("WAV sin cabecera RIFF.");
                reader.ReadUInt32();
                if (new string(reader.ReadChars(4)) != "WAVE") throw new InvalidDataException("WAV sin cabecera WAVE.");
                ushort format = 0, channels = 0, bits = 0;
                uint sampleRate = 0;
                byte[] data = null;
                while (reader.BaseStream.Position + 8 <= reader.BaseStream.Length)
                {
                    string chunk = new string(reader.ReadChars(4));
                    uint length = reader.ReadUInt32();
                    long next = reader.BaseStream.Position + length + (length & 1);
                    if (next > reader.BaseStream.Length) throw new InvalidDataException("Bloque WAV truncado.");
                    if (chunk == "fmt ")
                    {
                        if (length < 16) throw new InvalidDataException("Formato WAV incompleto.");
                        format = reader.ReadUInt16();
                        channels = reader.ReadUInt16();
                        sampleRate = reader.ReadUInt32();
                        reader.ReadUInt32();
                        reader.ReadUInt16();
                        bits = reader.ReadUInt16();
                    }
                    else if (chunk == "data")
                    {
                        if (length > int.MaxValue) throw new InvalidDataException("Audio demasiado grande.");
                        data = reader.ReadBytes((int)length);
                    }
                    reader.BaseStream.Position = next;
                }
                if (channels != 1 || sampleRate != 16000 || data == null)
                    throw new InvalidDataException("Se requiere WAV mono de 16 kHz.");
                if (format == 1 && bits == 16 && data.Length % 2 == 0) return data;
                if (format != 3 || bits != 32 || data.Length % 4 != 0)
                    throw new InvalidDataException("Se requiere PCM16 o IEEE float32.");
                var pcm = new byte[data.Length / 2];
                for (int i = 0, j = 0; i < data.Length; i += 4, j += 2)
                {
                    float value = BitConverter.ToSingle(data, i);
                    if (float.IsNaN(value)) value = 0;
                    value = Math.Max(-1f, Math.Min(1f, value));
                    short sample = (short)Math.Round(value < 0 ? value * 32768f : value * 32767f);
                    pcm[j] = (byte)sample;
                    pcm[j + 1] = (byte)(sample >> 8);
                }
                return pcm;
            }
        }
    }
}
