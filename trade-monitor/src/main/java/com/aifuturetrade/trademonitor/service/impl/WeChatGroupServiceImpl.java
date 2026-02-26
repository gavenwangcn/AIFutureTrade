package com.aifuturetrade.trademonitor.service.impl;

import com.aifuturetrade.trademonitor.dao.mapper.WeChatGroupMapper;
import com.aifuturetrade.trademonitor.entity.WeChatGroupDO;
import com.aifuturetrade.trademonitor.service.WeChatGroupService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 微信群配置服务实现类
 */
@Slf4j
@Service
public class WeChatGroupServiceImpl implements WeChatGroupService {

    @Autowired
    private WeChatGroupMapper weChatGroupMapper;

    @Autowired
    private RestTemplate restTemplate;

    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    @Override
    public IPage<WeChatGroupDO> queryPage(Integer page, Integer size, String groupName, Boolean isEnabled) {
        Page<WeChatGroupDO> pageParam = new Page<>(page, size);
        LambdaQueryWrapper<WeChatGroupDO> queryWrapper = new LambdaQueryWrapper<>();

        if (StringUtils.hasText(groupName)) {
            queryWrapper.like(WeChatGroupDO::getGroupName, groupName);
        }

        if (isEnabled != null) {
            queryWrapper.eq(WeChatGroupDO::getIsEnabled, isEnabled);
        }

        queryWrapper.orderByDesc(WeChatGroupDO::getCreatedAt);

        return weChatGroupMapper.selectPage(pageParam, queryWrapper);
    }

    @Override
    public List<WeChatGroupDO> queryEnabledGroups() {
        LambdaQueryWrapper<WeChatGroupDO> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(WeChatGroupDO::getIsEnabled, true);
        return weChatGroupMapper.selectList(queryWrapper);
    }

    @Override
    public WeChatGroupDO getById(Long id) {
        WeChatGroupDO weChatGroup = weChatGroupMapper.selectById(id);
        if (weChatGroup == null) {
            throw new RuntimeException("微信群配置不存在: " + id);
        }
        return weChatGroup;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public WeChatGroupDO create(WeChatGroupDO weChatGroup) {
        validateWeChatGroup(weChatGroup);

        LocalDateTime now = LocalDateTime.now();
        weChatGroup.setCreatedAt(now);
        weChatGroup.setUpdatedAt(now);

        if (weChatGroup.getIsEnabled() == null) {
            weChatGroup.setIsEnabled(true);
        }

        weChatGroupMapper.insert(weChatGroup);
        return weChatGroup;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public WeChatGroupDO update(Long id, WeChatGroupDO weChatGroup) {
        WeChatGroupDO existingGroup = getById(id);

        validateWeChatGroup(weChatGroup);

        existingGroup.setGroupName(weChatGroup.getGroupName());
        existingGroup.setWebhookUrl(weChatGroup.getWebhookUrl());
        existingGroup.setAlertTypes(weChatGroup.getAlertTypes());
        existingGroup.setIsEnabled(weChatGroup.getIsEnabled());
        existingGroup.setDescription(weChatGroup.getDescription());
        existingGroup.setUpdatedAt(LocalDateTime.now());

        weChatGroupMapper.updateById(existingGroup);
        return existingGroup;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long id) {
        WeChatGroupDO existingGroup = getById(id);
        weChatGroupMapper.deleteById(id);
        log.info("删除微信群配置: {}", existingGroup.getGroupName());
    }

    @Override
    public boolean testSend(Long id) {
        WeChatGroupDO weChatGroup = getById(id);

        String title = "测试通知";
        String message = "> **测试内容**: 这是一条测试消息\\n\\n" +
                "> **群组名称**: " + weChatGroup.getGroupName() + "\\n\\n" +
                "> **配置ID**: " + weChatGroup.getId();

        return sendToWebhook(weChatGroup.getWebhookUrl(), title, message);
    }

    /**
     * 验证微信群配置
     */
    private void validateWeChatGroup(WeChatGroupDO weChatGroup) {
        if (!StringUtils.hasText(weChatGroup.getGroupName())) {
            throw new IllegalArgumentException("群组名称不能为空");
        }

        if (!StringUtils.hasText(weChatGroup.getWebhookUrl())) {
            throw new IllegalArgumentException("Webhook URL不能为空");
        }

        if (!weChatGroup.getWebhookUrl().startsWith("http")) {
            throw new IllegalArgumentException("Webhook URL格式不正确");
        }
    }

    /**
     * 发送消息到企业微信Webhook
     */
    private boolean sendToWebhook(String webhookUrl, String title, String message) {
        try {
            String content = buildMarkdownContent(title, message);

            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("msgtype", "markdown");

            Map<String, String> markdown = new HashMap<>();
            markdown.put("content", content);
            requestBody.put("markdown", markdown);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<Map<String, Object>> request = new HttpEntity<>(requestBody, headers);

            Map<String, Object> response = restTemplate.postForObject(webhookUrl, request, Map.class);

            if (response != null && Integer.valueOf(0).equals(response.get("errcode"))) {
                log.info("微信通知发送成功: {}", title);
                return true;
            } else {
                log.error("微信通知发送失败: {}", response);
                return false;
            }
        } catch (Exception e) {
            log.error("发送微信通知异常: {}", webhookUrl, e);
            return false;
        }
    }

    /**
     * 构造Markdown格式内容
     */
    private String buildMarkdownContent(String title, String message) {
        StringBuilder sb = new StringBuilder();
        sb.append("### ").append(title).append("\\n\\n");
        sb.append("> **时间**: ").append(LocalDateTime.now().format(FORMATTER)).append("\\n\\n");
        sb.append(message);
        return sb.toString();
    }
}
