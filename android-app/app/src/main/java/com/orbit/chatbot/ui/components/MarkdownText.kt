package com.orbit.chatbot.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun MarkdownText(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.onSurface
) {
    val lines = text.split("\n")
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        var inCodeBlock = false
        val codeBlockLines = mutableListOf<String>()

        for (line in lines) {
            when {
                line.trimStart().startsWith("```") -> {
                    if (inCodeBlock) {
                        // End code block
                        CodeBlockCard(code = codeBlockLines.joinToString("\n"))
                        codeBlockLines.clear()
                        inCodeBlock = false
                    } else {
                        // Start code block
                        inCodeBlock = true
                    }
                }
                inCodeBlock -> {
                    codeBlockLines.add(line)
                }
                line.startsWith("### ") -> {
                    Text(
                        text = line.removePrefix("### "),
                        style = MaterialTheme.typography.titleMedium.copy(
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF00D2FF)
                        ),
                        modifier = Modifier.padding(top = 6.dp)
                    )
                }
                line.startsWith("## ") -> {
                    Text(
                        text = line.removePrefix("## "),
                        style = MaterialTheme.typography.titleLarge.copy(
                            fontWeight = FontWeight.ExtraBold,
                            color = Color(0xFF818CF8)
                        ),
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }
                line.startsWith("# ") -> {
                    Text(
                        text = line.removePrefix("# "),
                        style = MaterialTheme.typography.headlineSmall.copy(
                            fontWeight = FontWeight.Black,
                            color = Color(0xFF00D2FF)
                        ),
                        modifier = Modifier.padding(top = 10.dp)
                    )
                }
                line.trimStart().startsWith("- ") || line.trimStart().startsWith("* ") -> {
                    val content = line.trimStart().removePrefix("- ").removePrefix("* ")
                    Row(modifier = Modifier.padding(start = 8.dp)) {
                        Text("• ", color = Color(0xFF00D2FF), fontWeight = FontWeight.Bold)
                        Text(
                            text = parseInlineMarkdown(content),
                            style = MaterialTheme.typography.bodyMedium,
                            color = color
                        )
                    }
                }
                line.trimStart().startsWith("> ") -> {
                    val quote = line.trimStart().removePrefix("> ")
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp)
                            .clip(RoundedCornerShape(4.dp))
                            .background(Color(0xFF1E2638))
                            .padding(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        Text(
                            text = parseInlineMarkdown(quote),
                            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                            color = Color(0xFFCBD5E1)
                        )
                    }
                }
                else -> {
                    if (line.isNotEmpty()) {
                        Text(
                            text = parseInlineMarkdown(line),
                            style = MaterialTheme.typography.bodyMedium,
                            color = color
                        )
                    }
                }
            }
        }
        if (inCodeBlock && codeBlockLines.isNotEmpty()) {
            CodeBlockCard(code = codeBlockLines.joinToString("\n"))
        }
    }
}

@Composable
fun CodeBlockCard(code: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(Color(0xFF080B11))
            .border(1.dp, Color(0xFF1E2638), RoundedCornerShape(8.dp))
            .padding(12.dp)
    ) {
        Text(
            text = code,
            color = Color(0xFF38BDF8),
            fontFamily = FontFamily.Monospace,
            fontSize = 12.sp,
            lineHeight = 18.sp
        )
    }
}

fun parseInlineMarkdown(text: String) = buildAnnotatedString {
    var cursor = 0
    val boldRegex = Regex("""\*\*(.*?)\*\*""")
    val codeRegex = Regex("""`(.*?)`""")

    // Simple parser for bold and code
    var remaining = text
    var offset = 0

    while (offset < text.length) {
        val boldMatch = boldRegex.find(text, offset)
        val codeMatch = codeRegex.find(text, offset)

        val nextMatch = listOfNotNull(boldMatch, codeMatch).minByOrNull { it.range.first }

        if (nextMatch == null) {
            append(text.substring(offset))
            break
        }

        if (nextMatch.range.first > offset) {
            append(text.substring(offset, nextMatch.range.first))
        }

        if (nextMatch == boldMatch) {
            pushStyle(SpanStyle(fontWeight = FontWeight.Bold, color = Color.White))
            append(boldMatch.groupValues[1])
            pop()
        } else if (nextMatch == codeMatch) {
            pushStyle(
                SpanStyle(
                    fontFamily = FontFamily.Monospace,
                    background = Color(0xFF1E2638),
                    color = Color(0xFF00D2FF)
                )
            )
            append(" ${codeMatch!!.groupValues[1]} ")
            pop()
        }
        offset = nextMatch.range.last + 1
    }
}
